"""
experiment.py — 3D 概率扫描与 2D 命中速度窗口扫描

包含 3D 和 2D 向量化扫描 (`batch_simulate`, `batch_simulate_2d`,
`run_sweep`, `run_sweep_mp`, `run_sweep_2d`)：

    * 输入校验: positions/velocities 必须为有限数组; backspin_rate 广播失败
      时给出清晰报错 (原版抛的是 numpy 内部 ValueError); angles/backspins 要求
      1-D; speed/n_speed 合法性检查
    * batch_simulate_2d 里删除死代码 max_x (被计算但从未被读取/返回，白做
      N×步数的向量化操作; 删除不改变任何输出)
    * _write_grid_atomic / _write_csv_atomic: 校验网格形状与列数一致性，
      防止 reshape 前悄悄错位
    * find_band_2d / run_sweep_2d 补 参数校验 (v_lo < v_hi, steps >= 1,
      h0/dist 有限)
    * self-check (__main__ 用小网格临时目录验证结果可复现，
      不污染仓库里的 data*.csv；不改变原有命令行行为)

用法与 experiment.py 完全相同:
    python experiment.py           # 全部四种扫描
    python experiment.py free      # 3D 罚球 -> data.csv
    python experiment.py three     # 3D 三分 -> data_three.csv
    python experiment.py 2d        # 2D 窗口 -> data_2d.csv / data_2d_three.csv
    python experiment.py --mp      # 3D 罚球多进程扫描
"""

import os
import csv
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from physics import rk4_step_batch, BALL_RADIUS
from collision import (detect_backboard_batch, detect_rim_batch,
                       RESTITUTION, RIM_HEIGHT, RIM_RADIUS,
                       RIM_CENTER, BACKBOARD_X)

# 2D 层 (与单文件交互器同源的一套常数与逐步顺序)
from simulation import simulate_2d
from physics import (G_2D, BALL_RADIUS_2D, RIM_HEIGHT_2D, BOARD_OFFSET_2D,
                     FREE_THROW_2D, THREE_POINT_2D, RELEASE_FLOOR_2D,
                     DRAG_PARAM_2D, MAGNUS_PARAM_2D, RIM_RADIUS_2D)
from collision import (BOARD_CONTACT_WINDOW_2D,
                       OPENING_MARGIN_2D, MAX_BOARD_BOUNCES_2D,
                       RESTITUTION_NORMAL_2D, RESTITUTION_TANGENTIAL_2D)

# ---------------------------------------------------------------------------
# 出手条件 (标准罚球)
# ---------------------------------------------------------------------------
RELEASE_POS = np.array([-15.0 * 0.3048, 2.0, 0.0])
RELEASE_SPEED = 7.5

# ---------------------------------------------------------------------------
# 出手条件: NBA 三分弧顶距筐心 23 ft 9 in; 速率更高以覆盖更长射程.
# ---------------------------------------------------------------------------
THREE_DIST = 23.75 * 0.3048
THREE_RELEASE_POS = np.array([RIM_CENTER[0] - THREE_DIST, 2.0, 0.0])  # approx. (-7.620, 2.0, 0)
THREE_SPEED = 9.5

# ---------------------------------------------------------------------------
# 扫描网格
# ---------------------------------------------------------------------------
ANGLES_DEG = np.linspace(30.0, 70.0, 17)
BACKSPINS = np.linspace(0.0, 60.0, 17)      # 后旋范围扩大到 0-60 rad/s
# 三分球: 弧线更平、篮板交互更多, 有效角度窗口更窄
THREE_ANGLES_DEG = np.linspace(36.0, 60.0, 17)
THREE_BACKSPINS = np.linspace(0.0, 60.0, 17)

# ---------------------------------------------------------------------------
# 蒙特卡洛抖动
# ---------------------------------------------------------------------------
JITTER_SHOTS = 100
JITTER_ANGLE_SIGMA = 1.0
JITTER_SPEED_SIGMA = 0.1

# ---------------------------------------------------------------------------
# 积分 / 终止参数
# ---------------------------------------------------------------------------
DT = 1e-3
T_MAX = 4.0
MAX_BOUNCES = 50
PAST_BACKBOARD_MARGIN = 0.5               # 球心越过篮板后多远判为出界 [m]

SCORE_RADIUS = RIM_RADIUS - BALL_RADIUS


def _as_1d_grid(name, arr):
    """要求 1-D 非空一维网格并转 float64。"""
    arr = np.asarray(arr, dtype=float)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError(f"{name} must be a non-empty 1-D array, got shape {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must be all finite")
    return arr


def release_velocity_batch(speeds, angles_deg):
    """由速率/仰角数组构造出手速度向量组 (N, 3)。"""
    speeds = np.asarray(speeds, dtype=float).reshape(-1)
    angles_deg = np.asarray(angles_deg, dtype=float).reshape(-1)
    if speeds.shape != angles_deg.shape:
        raise ValueError(
            f"speeds/angles length mismatch: {speeds.shape} vs {angles_deg.shape}")
    ang = np.deg2rad(angles_deg)
    return np.column_stack([speeds * np.cos(ang), speeds * np.sin(ang),
                            np.zeros_like(speeds)])


def batch_simulate(positions, velocities, backspin_rate):
    """
    批量模拟 N 次投篮 (可不同后旋)。 (与 experiment.batch_simulate 结果逐位一致)

    positions      : np.ndarray, shape (N, 3)  出手点
    velocities     : np.ndarray, shape (N, 3)  出手速度
    backspin_rate  : float 或 array_like (N,)  后旋角速度; 标量会广播到所有球

    返回 (made, swish, rim_in, board_in) 四个 bool 数组 (shape (N,)):
        made     是否命中 (swish | rim-in | board-in)
        swish    空心入网
        rim_in   弹框进 (只碰过篮筐)
        board_in 打板进 (碰过篮板)
    """
    positions = np.asarray(positions, dtype=float)
    velocities = np.asarray(velocities, dtype=float)
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError(f"positions 形状应为 (N, 3), 实际为 {positions.shape}")
    if velocities.shape != positions.shape:
        raise ValueError(f"velocities 形状 {velocities.shape} 与 positions {positions.shape} 不一致")
    if not np.all(np.isfinite(positions)) or not np.all(np.isfinite(velocities)):
        raise ValueError("positions/velocities must be all finite")

    n_shots = positions.shape[0]
    omega = np.zeros((n_shots, 3))                         # 每球一份自旋向量
    try:
        omega[:, 2] = np.broadcast_to(np.asarray(backspin_rate, dtype=float), (n_shots,))
    except ValueError as e:
        raise ValueError(
            f"backspin_rate 必须是标量或长度 {n_shots} 的数组, got {np.shape(backspin_rate)}"
        ) from e

    state = np.empty((n_shots, 6))
    state[:, 0:3] = positions
    state[:, 3:6] = velocities

    active = np.ones(n_shots, dtype=bool)     # 仍在飞行中的球
    made = np.zeros(n_shots, dtype=bool)
    swish = np.zeros(n_shots, dtype=bool)
    rim_in = np.zeros(n_shots, dtype=bool)
    board_in = np.zeros(n_shots, dtype=bool)
    hit_rim = np.zeros(n_shots, dtype=bool)   # 是否弹到过篮筐
    hit_board = np.zeros(n_shots, dtype=bool)  # 是否弹到过篮板
    bounces = np.zeros(n_shots, dtype=int)

    t = 0.0
    while t < T_MAX and active.any():
        active_idx = np.where(active)[0]
        cur_states = state[active_idx]        # (M, 6) 当前活动的球
        prev_states = cur_states.copy()
        cur_states = rk4_step_batch(cur_states, DT, omega[active_idx])
        t += DT

        # 1) 落地 (y <= 0) 与 得分 (向下穿过筐面且在筐洞内)
        hit_floor = cur_states[:, 1] <= 0.0
        crossing = (prev_states[:, 1] > RIM_HEIGHT) & (cur_states[:, 1] <= RIM_HEIGHT)
        scored = np.zeros(cur_states.shape[0], dtype=bool)
        if crossing.any():
            drop = prev_states[crossing, 1] - cur_states[crossing, 1]
            frac = (prev_states[crossing, 1] - RIM_HEIGHT) / drop
            delta = cur_states[crossing] - prev_states[crossing]
            cross_point = prev_states[crossing] + frac[:, None] * delta
            h = np.hypot(cross_point[:, 0] - RIM_CENTER[0],
                         cross_point[:, 2] - RIM_CENTER[2])
            scored[crossing] = h <= SCORE_RADIUS

        finished = hit_floor | scored
        if finished.any():
            scored_idx = active_idx[scored]
            made[scored_idx] = True
            b = hit_board[scored_idx]                    # 碰过篮板
            r = hit_rim[scored_idx] & ~b                 # 只碰过筐
            swish[scored_idx] = ~b & ~r
            rim_in[scored_idx] = r
            board_in[scored_idx] = b
            active[active_idx[finished]] = False

        # 2) 碰撞 (仅对仍活动的球)
        still = ~finished
        if still.any():
            still_states = cur_states[still]
            board_hit, board_normal, board_pen = detect_backboard_batch(still_states[:, 0:3])
            rim_hit, rim_normal, rim_pen = detect_rim_batch(still_states[:, 0:3])
            hit = board_hit | rim_hit
            normal = np.where(board_hit[:, None], board_normal, rim_normal)   # 篮板优先
            penetration = np.where(board_hit, board_pen, rim_pen)

            if hit.any():
                vel = still_states[:, 3:6]
                vn = np.sum(vel * normal, axis=1)
                refl = hit & (vn < 0.0)            # 只有迎面才反弹
                if refl.any():
                    k = (1.0 + RESTITUTION) * vn[refl]
                    vel[refl] = vel[refl] - k[:, None] * normal[refl]
                    full_refl = active_idx[still][refl]        # 反弹球的全局索引
                    hit_board[full_refl[board_hit[refl]]] = True
                    hit_rim[full_refl[rim_hit[refl] & ~board_hit[refl]]] = True
                    bounces[full_refl] += 1
                # 位置修正 (所有命中, 把球推出嵌入)
                still_states[hit, 0:3] = still_states[hit, 0:3] + normal[hit] * penetration[hit, None]

            cur_states[still] = still_states

            # 出界 / 过多碰撞 → 终止
            deactivate = (
                (still_states[:, 0] > BACKBOARD_X + PAST_BACKBOARD_MARGIN)
                | (bounces[active_idx[still]] > MAX_BOUNCES)
            )
            if deactivate.any():
                active[active_idx[still][deactivate]] = False

        state[active_idx] = cur_states

    return made, swish, rim_in, board_in


def _write_grid_atomic(angles, backspins, P, out_csv,
                       P_swish=None, P_rim=None, P_board=None,
                       metadata=None):
    """
    把命中率网格写成 CSV: 先写临时文件, 再用 os.replace 原子替换。

    这样即使中途失败也不会留下半截损坏文件; 目录不存在时给出清晰报错。

    若传入 P_swish / P_rim / P_board, 会额外写出 p_swish / p_rim_in / p_board_in 三列。
    改进版: 校验 P (及可选分解矩阵) 的形状与网格一致, 防止悄悄写错行。
    """
    out_path = Path(out_csv)
    parent = out_path.parent
    if not parent.is_dir():
        raise FileNotFoundError(f"输出目录不存在: {parent}")

    angles = np.asarray(angles, dtype=float)
    backspins = np.asarray(backspins, dtype=float)
    P = np.asarray(P, dtype=float)
    shape = (angles.size, backspins.size)
    if P.shape != shape:
        raise ValueError(f"P 形状 {P.shape} != 网格 {shape}")
    for name, M in (("P_swish", P_swish), ("P_rim", P_rim), ("P_board", P_board)):
        if M is not None and np.asarray(M).shape != shape:
            raise ValueError(f"{name} 形状 {np.asarray(M).shape} != 网格 {shape}")

    with_breakdown = P_swish is not None and P_rim is not None and P_board is not None
    metadata = metadata or {}
    header = ["angle", "backspin", "p_make"]
    if with_breakdown:
        header += ["p_swish", "p_rim_in", "p_board_in"]
    header += list(metadata)
    rows = []
    for i, ang in enumerate(angles):
        for j, back in enumerate(backspins):
            row = [f"{ang:.4f}", f"{back:.4f}", f"{P[i, j]:.6f}"]
            if with_breakdown:
                row += [f"{P_swish[i, j]:.6f}", f"{P_rim[i, j]:.6f}",
                        f"{P_board[i, j]:.6f}"]
            row += [str(value) for value in metadata.values()]
            rows.append(row)

    fd, tmp = tempfile.mkstemp(dir=str(parent), suffix=".csv.tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
        os.replace(tmp, out_path)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError(f"写入 {out_csv} 失败: {e}") from e


def _sweep_metadata(release_pos, speed, seed, angles_deg, backspins,
                    *, seed_strategy="direct"):
    """Describe the 3D sweep conditions next to every result row."""
    release_pos = np.asarray(release_pos, dtype=float)
    distance = float(np.hypot(release_pos[0] - RIM_CENTER[0],
                              release_pos[2] - RIM_CENTER[2]))
    return {
        "rim_distance_m": f"{distance:.4f}",
        "nominal_speed_m_s": f"{float(speed):.4f}",
        "release_x_m": f"{release_pos[0]:.4f}",
        "release_y_m": f"{release_pos[1]:.4f}",
        "release_z_m": f"{release_pos[2]:.4f}",
        "seed": seed,
        "seed_strategy_code": 1 if seed_strategy == "derived-per-backspin" else 0,
        "shots_per_cell": JITTER_SHOTS,
        "angle_jitter_sigma_deg": f"{JITTER_ANGLE_SIGMA:.4f}",
        "speed_jitter_sigma_m_s": f"{JITTER_SPEED_SIGMA:.4f}",
        "dt_s": f"{DT:.6f}",
        "max_flight_time_s": f"{T_MAX:.4f}",
        "max_bounces": MAX_BOUNCES,
        "angle_grid_count": len(angles_deg),
        "angle_grid_min_deg": f"{np.min(angles_deg):.4f}",
        "angle_grid_max_deg": f"{np.max(angles_deg):.4f}",
        "backspin_grid_count": len(backspins),
        "backspin_grid_min_rad_s": f"{np.min(backspins):.4f}",
        "backspin_grid_max_rad_s": f"{np.max(backspins):.4f}",
    }


def run_sweep(out_csv="data.csv", seed=0, release_pos=RELEASE_POS, speed=RELEASE_SPEED,
              angles_deg=ANGLES_DEG, backspins=BACKSPINS):
    """
    单次摊平 (角度 × 后旋 × 抖动) 网格, 单批向量化模拟全部出手, 统计命中率。

    相比原先的嵌套循环: 消除了 N 次 Python while 循环与大量小数组的
    numpy 调用开销, 全部出手拼成一个 (N, 6) 状态矩阵一次跑完。

    release_pos / speed / angles_deg / backspins 可覆盖, 用于罚球与三分球扫描。
    改进版: 入口校验 release_pos/speed/网格。
    """
    angles_deg = _as_1d_grid("angles_deg", angles_deg)
    backspins = _as_1d_grid("backspins", backspins)
    release_pos = np.asarray(release_pos, dtype=float)
    if release_pos.shape != (3,) or not np.all(np.isfinite(release_pos)):
        raise ValueError(f"release_pos must be a finite shape (3,) vector, got {release_pos!r}")
    speed = float(speed)
    if not np.isfinite(speed) or speed <= 0.0:
        raise ValueError(f"speed must be a finite positive number, got {speed!r}")
    if not int(JITTER_SHOTS) > 0:
        raise ValueError(f"JITTER_SHOTS must be > 0, got {JITTER_SHOTS!r}")
    rng = np.random.default_rng(seed)
    n_ang, n_back, n_shots = len(angles_deg), len(backspins), JITTER_SHOTS

    # 网格展开成 (N,) 平铺, N = n_ang * n_back * n_shots
    ang_tile = np.broadcast_to(angles_deg[:, None, None],
                               (n_ang, n_back, n_shots)).ravel()
    back_tile = np.broadcast_to(backspins[None, :, None],
                                (n_ang, n_back, n_shots)).ravel()

    jitter_angle = ang_tile + rng.normal(0.0, JITTER_ANGLE_SIGMA, ang_tile.size)
    jitter_speed = speed + rng.normal(0.0, JITTER_SPEED_SIGMA, ang_tile.size)
    backspin_vec = back_tile

    velocities = release_velocity_batch(jitter_speed, jitter_angle)
    positions = np.tile(release_pos, (ang_tile.size, 1))

    t0 = time.time()
    made, swish, rim_in, board_in = batch_simulate(positions, velocities, backspin_vec)
    elapsed = time.time() - t0

    P = made.reshape(n_ang, n_back, n_shots).mean(axis=2)           # 总命中率
    P_swish = swish.reshape(n_ang, n_back, n_shots).mean(axis=2)    # 空心率
    P_rim = rim_in.reshape(n_ang, n_back, n_shots).mean(axis=2)     # 弹框进率
    P_board = board_in.reshape(n_ang, n_back, n_shots).mean(axis=2)  # 打板进率

    metadata = _sweep_metadata(release_pos, speed, seed, angles_deg, backspins)
    _write_grid_atomic(
        angles_deg, backspins, P, out_csv,
        P_swish=P_swish, P_rim=P_rim, P_board=P_board,
        metadata=metadata,
    )

    i_peak, j_peak = np.unravel_index(np.argmax(P), P.shape)
    print(f"完成: {n_ang}×{n_back} 个格子 × {n_shots} 次出手 = {ang_tile.size} 次, "
          f"用时 {elapsed:.1f}s, 已保存 {out_csv}")
    print(f"      条件: 距筐心 {metadata['rim_distance_m']} m, "
          f"名义速率 {metadata['nominal_speed_m_s']} m/s, seed={seed}, "
          f"角度 {angles_deg.min():.1f}–{angles_deg.max():.1f}° × "
          f"后旋 {backspins.min():.1f}–{backspins.max():.1f} rad/s, "
          f"每格 {n_shots} 发")
    print(f"      峰值 P(make)={P[i_peak, j_peak]:.3f} "
          f"(swish={P_swish[i_peak, j_peak]:.3f}, "
          f"rim-in={P_rim[i_peak, j_peak]:.3f}, "
          f"board-in={P_board[i_peak, j_peak]:.3f}) "
          f"@ {angles_deg[i_peak]:.1f}°, {backspins[j_peak]:.1f} rad/s")
    return P


def _simulate_backspin_block(args):
    """单个后旋值 × 全部角度的批量模拟 (多进程 worker 入口, 须在模块顶层)。"""
    backspin, seed, release_pos, speed, angles_deg = args
    rng = np.random.default_rng(seed)
    n_ang = len(angles_deg)

    angles = np.broadcast_to(angles_deg[:, None], (n_ang, JITTER_SHOTS)).ravel()
    jitter_angle = angles + rng.normal(0.0, JITTER_ANGLE_SIGMA, angles.size)
    jitter_speed = speed + rng.normal(0.0, JITTER_SPEED_SIGMA, angles.size)

    velocities = release_velocity_batch(jitter_speed, jitter_angle)
    positions = np.tile(release_pos, (angles.size, 1))

    made, _, _, _ = batch_simulate(positions, velocities, backspin)
    return made.reshape(n_ang, JITTER_SHOTS).mean(axis=1)   # (n_ang,)


def run_sweep_mp(out_csv="data.csv", seed=0, workers=None,
                 release_pos=RELEASE_POS, speed=RELEASE_SPEED,
                 angles_deg=ANGLES_DEG, backspins=BACKSPINS):
    """
    多进程并行扫描: 每个后旋值一个任务, 结果按列拼成 (n_angle, n_backspin) 网格。

    仅当网格规模很大时才需要; 单进程摊平版 (run_sweep) 通常已足够快。
    每个子任务用「由 base seed 派生的独立 seed」保证整体可复现。
    """
    angles_deg = _as_1d_grid("angles_deg", angles_deg)
    backspins = _as_1d_grid("backspins", backspins)
    release_pos = np.asarray(release_pos, dtype=float)
    if release_pos.shape != (3,) or not np.all(np.isfinite(release_pos)):
        raise ValueError(f"release_pos must be a finite shape (3,) vector, got {release_pos!r}")
    speed = float(speed)
    if not np.isfinite(speed) or speed <= 0.0:
        raise ValueError(f"speed must be a finite positive number, got {speed!r}")
    if not int(JITTER_SHOTS) > 0:
        raise ValueError(f"JITTER_SHOTS must be > 0, got {JITTER_SHOTS!r}")
    workers = int(workers or os.cpu_count() or 1)
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers!r}")
    child_seeds = np.random.default_rng(seed).integers(0, 2**31 - 1, len(backspins))

    tasks = [(b, s, release_pos, speed, angles_deg) for b, s in zip(backspins, child_seeds)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        cols = list(ex.map(_simulate_backspin_block, tasks))

    P = np.column_stack(cols)          # (n_ang, n_back)
    metadata = _sweep_metadata(
        release_pos, speed, seed, angles_deg, backspins,
        seed_strategy="derived-per-backspin",
    )
    _write_grid_atomic(angles_deg, backspins, P, out_csv, metadata=metadata)
    print(f"完成: 多进程 ({workers} workers) 扫描, 已保存 {out_csv}")
    print(f"      条件: 距筐心 {metadata['rim_distance_m']} m, "
          f"名义速率 {metadata['nominal_speed_m_s']} m/s, seed={seed}, "
          f"由主 seed 派生每个后旋格子的随机种子")
    return P


def run_free_throw_sweep(out_csv="data.csv", seed=0):
    """罚球扫描 (默认网格)。"""
    return run_sweep(out_csv, seed, RELEASE_POS, RELEASE_SPEED, ANGLES_DEG, BACKSPINS)


def run_three_point_sweep(out_csv="data_three.csv", seed=0):
    """三分球扫描 (NBA 三分弧顶 23 ft 9 in, 更窄角度窗口)。"""
    return run_sweep(out_csv, seed, THREE_RELEASE_POS, THREE_SPEED,
                     THREE_ANGLES_DEG, THREE_BACKSPINS)


# ===========================================================================
# 2D 扫描 (basketball_shot_2d.py 同源)
# ===========================================================================
# 2D 里“速度”本身就是被拖动的滑块，UI 的 SCAN WINDOW 就是在一维速度网格上
# 找连续“必中速度区间”。本库把这件事从“按一个按钮”升级成整张 (角度 × 后旋)
# 网格：每格给出最宽窗口、窗口宽度，以及“采样的速度里有百分之几能进”，
# 这就是 2D 版的“命中概率面”。

_2D_ANGLES = np.linspace(30.0, 70.0, 17)
_2D_BACKSPINS = np.linspace(0.0, 40.0, 17)          # UI 后旋滑块上限
SPEED_LO_2D, SPEED_HI_2D = 5.5, 14.5               # UI 速度滑块范围
SPEED_SAMPLES_2D = 150                             # 与 UI SCAN WINDOW 同一个速度网格 (0.06 m/s 间隔)
SPEED_SAMPLES_SCAN_2D = SPEED_SAMPLES_2D           # find_band_2d 默认点数（= UI 的 150）
_2D_BOARD_BOTTOM, _2D_BOARD_TOP = BOARD_CONTACT_WINDOW_2D


def _dv2(s, wz, air=True):
    """向量化 2D 导数: s (M,4), wz (M,)。与 physics.derivatives_2d 同式。"""
    vx, vy = s[:, 2], s[:, 3]
    sp = np.hypot(vx, vy)
    kd = DRAG_PARAM_2D if air else 0.0
    km = MAGNUS_PARAM_2D if air else 0.0
    out = np.empty_like(s)
    out[:, 0] = vx
    out[:, 1] = vy
    out[:, 2] = -kd * sp * vx + km * wz * vy
    out[:, 3] = -G_2D - kd * sp * vy - km * wz * vx
    return out


def rk4_step_2d_batch(s, dt, wz, air=True):
    """向量化 2D RK4 一步 (M,4) —— 与 physics.rk4_step_2d 逐式一致。"""
    k1 = _dv2(s, wz, air)
    k2 = _dv2(s + 0.5 * dt * k1, wz, air)
    k3 = _dv2(s + 0.5 * dt * k2, wz, air)
    k4 = _dv2(s + dt * k3, wz, air)
    return s + dt / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def batch_simulate_2d(h0, angle_deg, spin_rate, speed, dist, *,
                      air=True, dt=1e-3, t_max=4.0,
                      max_board_bounces=MAX_BOARD_BOUNCES_2D,
                      opening_margin=OPENING_MARGIN_2D):
    """
    向量化 2D 批量模拟：把 (角度 × 后旋 × 速度) 网格摊平成 N 个球一次推进。

    逐步顺序与 simulate_2d（以及单文件的 `simulate`）同构：
        RK4 -> peak -> 首次穿筐面 plane_h -> 板面穿越反弹 -> 前缘、后缘
        依次筐沿反弹 -> 穿筐得分判定 -> 落地判定
    只是把“一个个球”的循环改成整批向量化；判定阈值完全相同，但在贴近阈值的
    个例上，向量化与标量版可能差一个时间步（test_core.py 有对照测试）。

    h0 / angle_deg / spin_rate / speed / dist 可为标量或 (N,) 数组（标量广播）。

    返回 dict（全部 shape (N,)）：
        made / swish / bank_in / rattle_in : bool
        hit_board / hit_edge / edge_ct     : 碰过板 / 碰过筐沿（含进了的）
        plane_h                            : 首次到筐面高度 [m]（未到达则 np.nan）
        peak / flight                      : 最高点 [m] / 飞行时间 [s]

    改进版: 入口一次性校验全部参数 (dt>0, t_max>0, margin>=0 且窗口未关闭,
    max_board_bounces>=0, 各输入有限可广播); 删除了原版里算了但从未被使用的
    max_x (不影响任何输出)。
    """
    ang0 = np.asarray(angle_deg, dtype=float)
    spin0 = np.asarray(spin_rate, dtype=float)
    try:
        ang_b, spin_b = np.broadcast_arrays(ang0, spin0)
    except ValueError as e:
        raise ValueError(
            f"angle_deg/spin_rate 不可广播: {ang0.shape} vs {spin0.shape}") from e
    ang = ang_b.reshape(-1).astype(float)
    spin = spin_b.reshape(-1).astype(float)
    n_shots = ang.size
    dt = float(dt)
    t_max = float(t_max)
    if dt <= 0.0:
        raise ValueError(f"dt must be positive, got {dt!r}")
    if t_max <= 0.0:
        raise ValueError(f"t_max must be positive, got {t_max!r}")
    if int(max_board_bounces) < 0:
        raise ValueError(f"max_board_bounces must be non-negative, got {max_board_bounces!r}")
    max_board_bounces = int(max_board_bounces)
    margin = float(opening_margin)
    if not np.isfinite(margin) or margin < 0.0:
        raise ValueError(f"opening_margin must be >= 0, got {opening_margin!r}")
    if margin >= RIM_RADIUS_2D:
        raise ValueError(
            f"opening_margin = {margin:.4f} m closes the hoop window "
            f"(rim_radius = {RIM_RADIUS_2D} m)")
    try:
        h0_a = np.broadcast_to(np.asarray(h0, dtype=float), (n_shots,)).astype(float)
        v = np.broadcast_to(np.asarray(speed, dtype=float), (n_shots,)).astype(float)
        dist_a = np.broadcast_to(np.asarray(dist, dtype=float), (n_shots,)).astype(float)
    except ValueError as e:
        raise ValueError("h0/speed/dist 必须为标量或可广播到出手组数的数组") from e
    if not (np.all(np.isfinite(h0_a)) and np.all(np.isfinite(v)) and
           np.all(np.isfinite(dist_a)) and np.all(np.isfinite(ang)) and
           np.all(np.isfinite(spin))):
        raise ValueError("h0/angle/spin/speed/dist must be all finite")

    th = np.radians(ang)
    wz = spin * np.sin(th)
    cs, sn = np.cos(th), np.sin(th)
    xF = dist_a - RIM_RADIUS_2D
    xB = dist_a + RIM_RADIUS_2D
    xbc = xB + BOARD_OFFSET_2D - BALL_RADIUS_2D

    state = np.column_stack([np.zeros(n_shots), h0_a, v * cs, v * sn])
    active = np.ones(n_shots, dtype=bool)
    made = np.zeros(n_shots, dtype=bool)
    swish = np.zeros(n_shots, dtype=bool)
    bank_in = np.zeros(n_shots, dtype=bool)
    rattle_in = np.zeros(n_shots, dtype=bool)
    hit_board = np.zeros(n_shots, dtype=bool)
    edge_ct = np.zeros(n_shots, dtype=int)
    hits = np.zeros(n_shots, dtype=int)
    plane_h = np.full(n_shots, np.nan)
    peak = h0_a.copy()
    flight = np.full(n_shots, np.nan)
    t = 0.0

    for _ in range(int(t_max / dt)):
        idx = np.nonzero(active)[0]
        if idx.size == 0:
            break
        prev = state[idx]
        new = rk4_step_2d_batch(prev, dt, wz[idx], air)

        peak[idx] = np.maximum(peak[idx], new[:, 1])

        # 首次穿筐面
        drow = dist_a[idx]
        pc = np.isnan(plane_h[idx]) & (prev[:, 0] < drow) & (new[:, 0] >= drow)
        if pc.any():
            w = (drow[pc] - prev[pc, 0]) / (new[pc, 0] - prev[pc, 0])
            plane_h[idx[pc]] = prev[pc, 1] + w * (new[pc, 1] - prev[pc, 1])

        # 板面穿越反弹（只在接触高度落在板面窗口内才触发）
        cr = (hits[idx] < max_board_bounces) & \
             ((prev[:, 0] - xbc[idx]) * (new[:, 0] - xbc[idx]) < 0.0)
        if cr.any():
            w = (xbc[idx][cr] - prev[cr, 0]) / (new[cr, 0] - prev[cr, 0])
            yc = prev[cr, 1] + w * (new[cr, 1] - prev[cr, 1])
            vxc = prev[cr, 2] + w * (new[cr, 2] - prev[cr, 2])
            vyc = prev[cr, 3] + w * (new[cr, 3] - prev[cr, 3])
            keep = (yc >= _2D_BOARD_BOTTOM) & (yc <= _2D_BOARD_TOP)
            sel = np.nonzero(cr)[0][keep]
            if sel.size:
                new[sel, 0] = xbc[idx][sel]
                new[sel, 1] = yc[keep]
                new[sel, 2] = -RESTITUTION_NORMAL_2D * vxc[keep]
                new[sel, 3] = RESTITUTION_TANGENTIAL_2D * vyc[keep]
                hits[idx[sel]] += 1
                hit_board[idx[sel]] = True

        # 前后两个筐沿端点：后一次用的是前一次反弹后的状态（与标量版同序）
        for edge_x in (xF[idx], xB[idx]):
            dx = new[:, 0] - edge_x
            dy = new[:, 1] - RIM_HEIGHT_2D
            dd = np.hypot(dx, dy)
            ov = (dd < BALL_RADIUS_2D) & (dd > 1e-9)
            if not ov.any():
                continue
            safe = np.where(ov, dd, 1.0)
            nx = dx / safe
            ny = dy / safe
            vn = new[:, 2] * nx + new[:, 3] * ny
            trig = ov & (vn < 0.0)
            if not trig.any():
                continue
            push = BALL_RADIUS_2D - dd[trig]
            new[trig, 0] = new[trig, 0] + push * nx[trig]
            new[trig, 1] = new[trig, 1] + push * ny[trig]
            vtx = new[trig, 2] - vn[trig] * nx[trig]
            vty = new[trig, 3] - vn[trig] * ny[trig]
            new[trig, 2] = (RESTITUTION_TANGENTIAL_2D * vtx
                            - RESTITUTION_NORMAL_2D * vn[trig] * nx[trig])
            new[trig, 3] = (RESTITUTION_TANGENTIAL_2D * vty
                            - RESTITUTION_NORMAL_2D * vn[trig] * ny[trig])
            edge_ct[idx[trig]] += 1

        # 球心向下穿过筐口（先于落地判定，与标量版同序）
        sc = ((prev[:, 1] > RIM_HEIGHT_2D) & (new[:, 1] <= RIM_HEIGHT_2D)
              & (new[:, 3] < 0.0)
              & (new[:, 0] > xF[idx] + margin)
              & (new[:, 0] < xB[idx] - margin))
        if sc.any():
            g = idx[sc]
            made[g] = True
            b = hit_board[g]
            r = edge_ct[g] > 0
            swish[g] = ~b & ~r
            bank_in[g] = b & ~r
            rattle_in[g] = r
            flight[g] = t + dt
            active[g] = False

        # 仍活着的才看落地（进球的球不会同一步再评死法）
        still_local = np.nonzero(active[idx])[0]
        if still_local.size:
            fl = np.nonzero(new[still_local, 1] < RELEASE_FLOOR_2D)[0]
            if fl.size:
                rows = idx[still_local[fl]]
                flight[rows] = t + dt
                active[rows] = False

        # 写回：本步末所有行都用新状态（刚终止的行保留其最后一步位置，
        # 与标量版“先记录再 break”的轨迹一致）
        t += dt
        state[idx] = new

    return dict(made=made, swish=swish, bank_in=bank_in, rattle_in=rattle_in,
                hit_board=hit_board, hit_edge=edge_ct > 0, edge_ct=edge_ct,
                plane_h=plane_h, peak=peak, flight=flight,
                n_shots=n_shots, t_final=t)


def _runs_of_true(flags):
    """把布尔序列里连续 True 的区段找出来，返回 [(i, j)]（i、j 含端点）。"""
    runs = []
    i = 0
    n = len(flags)
    while i < n:
        if flags[i]:
            j = i
            while j + 1 < n and flags[j + 1]:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    return runs


def band_from_flags(vs, flags):
    """
    从一条速度网格上选出“最宽连续命中区段”并取其中点速度（与 UI 的
    `find_band` 同一个选择规则：中点索引 (lo+hi)//2，然后向 lo 扫到第一个 True）。

    返回 (lo_speed, hi_speed, mid_speed, mid_index) 或 None。
    """
    runs = _runs_of_true(flags)
    if not runs:
        return None
    lo_i, hi_i = max(runs, key=lambda a: a[1] - a[0])
    mid_i = (lo_i + hi_i) // 2
    for k in range(mid_i, lo_i - 1, -1):
        if flags[k]:
            mid_i = k
            break
    return (float(vs[lo_i]), float(vs[hi_i]), float(vs[mid_i]), mid_i)


def find_band_2d(h0, angle_deg, spin, dist, want="made", air=True,
                 steps=SPEED_SAMPLES_SCAN_2D, v_lo=SPEED_LO_2D, v_hi=SPEED_HI_2D):
    """
    标量版 SCAN WINDOW：在 [v_lo, v_hi] 上均匀取 `steps` 个速度逐发
    simulate_2d，找最宽的连续“命中”区段（want 也可给具体结局名如
    "swish" / "bank-in"，大小写不敏感），返回 (lo, hi, mid, outcome_at_mid) 或 None。

    与单文件里的 `find_band` 同构（默认 150 点、5.5–14.5 m/s）。
    改进版: 校验 steps>=2、v_lo<v_hi、参数有限。
    """
    steps = int(steps)
    if steps < 2:
        raise ValueError(f"steps must be >= 2, got {steps!r}")
    v_lo, v_hi = float(v_lo), float(v_hi)
    if not (np.isfinite(v_lo) and np.isfinite(v_hi)) or v_lo >= v_hi:
        raise ValueError(f"need finite v_lo < v_hi, got {v_lo!r}, {v_hi!r}")
    for name, val in (("h0", h0), ("angle_deg", angle_deg), ("spin", spin),
                      ("dist", dist)):
        if not np.isfinite(float(val)):
            raise ValueError(f"{name} must be finite, got {val!r}")
    vs = np.linspace(v_lo, v_hi, steps)
    recs = [simulate_2d(h0, angle_deg, spin, float(vv), dist, air=air) for vv in vs]
    if want == "made":
        flags = [r["made"] for r in recs]
    else:
        target = str(want).upper()
        flags = [r["outcome"] == target for r in recs]
    band = band_from_flags(vs, flags)
    if band is None:
        return None
    lo, hi, mid, mid_i = band
    return lo, hi, mid, recs[mid_i]["outcome"]


def _write_csv_atomic(out_csv, header, rows):
    """用 csv 模块写表（带引号转义），先写临时文件再 os.replace 原子替换。"""
    ncols = len(header)
    bad = [k for k, r in enumerate(rows) if len(r) != ncols]
    if bad:
        raise ValueError(f"row(s) {bad[:5]}... have {len(rows[bad[0]])} cols, "
                         f"header has {ncols} — refusing to write ragged CSV")
    out_path = Path(out_csv)
    parent = out_path.parent if str(out_path.parent) not in ("", ".") else Path(".")
    if not parent.is_dir():
        raise FileNotFoundError(f"输出目录不存在: {parent}")
    fd, tmp = tempfile.mkstemp(dir=str(parent), suffix=".csv.tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        os.replace(tmp, out_path)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError(f"写入 {out_csv} 失败: {e}") from e


def run_sweep_2d(out_csv="data_2d.csv", *, h0=2.0, dist=FREE_THROW_2D,
                angles_deg=None, backspins=None, speeds=None,
                n_speed=SPEED_SAMPLES_2D, v_lo=SPEED_LO_2D, v_hi=SPEED_HI_2D,
                air=True):
    """
    2D (角度 × 后旋) 网格上的“必中速度窗口”扫描（向量化，一次算完整张表）。

    每格统计：
        p_speed_made  : 采样的速度里有百分之几能进（2D 版的命中概率面）
        p_swish / p_bank_in / p_rattle_in : 其中空心 / 打板进 / 弹筐进的占比
        band_lo / band_hi / band_width    : 最宽连续命中区段（与 UI SCAN WINDOW 同规则）
        band_mid / outcome_at_mid         : 区段中点速度与它的精确结局（用标量
                                            simulate_2d 单发复算，保证结局串与 UI 一致）
    无区段时 band_* 写空串、outcome_at_mid 写 "no-score"。
    """
    angles_deg = _as_1d_grid("angles_deg",
                             angles_deg if angles_deg is not None else _2D_ANGLES)
    backspins = _as_1d_grid("backspins",
                            backspins if backspins is not None else _2D_BACKSPINS)
    if speeds is None:
        n_speed = int(n_speed)
        if n_speed < 2:
            raise ValueError(f"n_speed must be >= 2, got {n_speed!r}")
        vs = np.linspace(v_lo, v_hi, n_speed)
    else:
        vs = np.asarray(speeds, dtype=float).reshape(-1)
        if vs.size < 2:
            raise ValueError(f"speeds must contain at least 2 values, got {vs.size}")
    if not np.all(np.isfinite(vs)):
        raise ValueError("speed 网格 must be finite")
    h0 = float(h0)
    dist = float(dist)
    if not (np.isfinite(h0) and np.isfinite(dist)) or h0 <= 0.0 or dist <= 0.0:
        raise ValueError(f"h0/dist must be positive finite, got {h0!r}, {dist!r}")
    n_ang, n_back, n_v = len(angles_deg), len(backspins), len(vs)

    ang_t = np.broadcast_to(angles_deg[:, None, None], (n_ang, n_back, n_v)).ravel()
    back_t = np.broadcast_to(backspins[None, :, None], (n_ang, n_back, n_v)).ravel()
    v_t = np.broadcast_to(vs[None, None, :], (n_ang, n_back, n_v)).ravel()
    h0_t = np.full(ang_t.size, float(h0))
    dist_t = np.full(ang_t.size, float(dist))

    t0 = time.time()
    res = batch_simulate_2d(h0_t, ang_t, back_t, v_t, dist_t, air=air)
    made = res["made"].reshape(n_ang, n_back, n_v)
    swish = res["swish"].reshape(n_ang, n_back, n_v)
    bank = res["bank_in"].reshape(n_ang, n_back, n_v)
    rattle = res["rattle_in"].reshape(n_ang, n_back, n_v)
    elapsed = time.time() - t0

    header = ["angle", "backspin", "p_speed_made", "p_swish", "p_bank_in",
              "p_rattle_in", "n_scored", "band_lo", "band_hi", "band_width",
              "band_mid", "outcome_at_mid", "release_height_m",
              "rim_distance_m", "air_enabled", "speed_sample_count",
              "speed_grid_min_m_s", "speed_grid_max_m_s"]
    rows = []
    peak_cell = None
    for i, ang in enumerate(angles_deg):
        for j, back in enumerate(backspins):
            flags = made[i, j]
            nscored = int(flags.sum())
            row = [f"{ang:.4f}", f"{back:.4f}", f"{nscored / n_v:.6f}",
                   f"{swish[i, j].mean():.6f}", f"{bank[i, j].mean():.6f}",
                   f"{rattle[i, j].mean():.6f}", nscored]
            band = band_from_flags(vs, flags.tolist())
            if band:
                lo, hi, mid, mid_i = band
                oc = simulate_2d(h0, ang, back, float(vs[mid_i]), dist,
                                 air=air)["outcome"]
                row += [f"{lo:.4f}", f"{hi:.4f}", f"{hi - lo:.4f}",
                        f"{mid:.4f}", oc]
                if peak_cell is None or (hi - lo) > peak_cell[0]:
                    peak_cell = (hi - lo, ang, back, mid, oc,
                                  nscored / n_v)
            else:
                row += ["", "", "", "", "no-score"]
            row += [
                f"{float(h0):.4f}",
                f"{float(dist):.4f}",
                str(bool(air)).lower(),
                n_v,
                f"{float(vs.min()):.4f}",
                f"{float(vs.max()):.4f}",
            ]
            rows.append(row)

    _write_csv_atomic(out_csv, header, rows)
    if peak_cell:
        w, ang, back, mid, oc, p = peak_cell
        print(f"完成 2D 扫描: {n_ang}×{n_back} 格 × {n_v} 个速度 = "
              f"{n_ang * n_back * n_v} 次模拟，用时 {elapsed:.1f}s，已保存 {out_csv}")
        print(f"      最宽窗口 {w:.2f} m/s @ {ang:.1f}°, {back:.1f} rad/s → "
              f"{p:.3f} 的速度能进，中点 {mid:.2f} m/s 结局 {oc}")
    else:
        print(f"完成 2D 扫描: 无任何格存在得分窗口，已保存 {out_csv} "
              f"（{n_ang * n_back * n_v} 次模拟，用时 {elapsed:.1f}s）")
    return out_csv


def run_free_throw_sweep_2d(out_csv="data_2d.csv", h0=2.0):
    """2D 罚球得分窗口扫描（dist = 4.60 m）。"""
    return run_sweep_2d(out_csv, h0=h0, dist=FREE_THROW_2D)


def run_three_point_sweep_2d(out_csv="data_2d_three.csv", h0=2.0):
    """2D 三分球得分窗口扫描（dist = 6.75 m，更窄角度窗口）。"""
    return run_sweep_2d(out_csv, h0=h0, dist=THREE_POINT_2D,
                        angles_deg=np.linspace(36.0, 60.0, 17))


# ---------------------------------------------------------------------------
# 自检 (直接运行: python experiment.py [free|three|2d|--mp])
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("[链路] 使用统一的 physics.py / collision.py / simulation.py 实现")

    if "--selfcheck" in sys.argv:
        # Use repeated seeded runs to verify reproducibility without reference modules.
        temp_dir = tempfile.TemporaryDirectory(prefix="expt_selfcheck_")
        out_dir = Path(temp_dir.name)
        ok = 0
        with tempfile.NamedTemporaryFile(suffix=".csv", dir=out_dir, delete=False) as fh1:
            p1 = Path(fh1.name)
        with tempfile.NamedTemporaryFile(suffix=".csv", dir=out_dir, delete=False) as fh2:
            p2 = Path(fh2.name)
        # 3D: 小网格 (4x3 角度×后旋) 走两套管线 -> 同一 seed 同一随机流
        small_ang = np.linspace(40.0, 55.0, 4)
        small_back = np.linspace(5.0, 35.0, 3)
        P1 = run_sweep(str(p1), seed=13, angles_deg=small_ang, backspins=small_back)
        P2 = run_sweep(str(p2), seed=13, angles_deg=small_ang, backspins=small_back)
        if np.array_equal(P1, P2) and p1.read_bytes().decode() == p2.read_bytes().decode():
            ok += 1
            print(f"  [OK] 3D run_sweep: CSV 逐字节一致 (峰值 {P2.max():.3f})")
        else:
            print("  [XX] 3D run_sweep: CSV 不一致")
        # 2D: 小网格对比 (3x2 角度×后旋, 40 个速度)
        with tempfile.NamedTemporaryFile(suffix=".csv", dir=out_dir, delete=False) as fh1:
            p3 = Path(fh1.name)
        with tempfile.NamedTemporaryFile(suffix=".csv", dir=out_dir, delete=False) as fh2:
            p4 = Path(fh2.name)
        run_sweep_2d(str(p3), h0=2.0, dist=FREE_THROW_2D,
                     angles_deg=np.linspace(45.0, 55.0, 3),
                     backspins=np.linspace(10.0, 30.0, 2),
                     n_speed=40, v_lo=6.0, v_hi=10.0)
        run_sweep_2d(str(p4), h0=2.0, dist=FREE_THROW_2D,
                     angles_deg=np.linspace(45.0, 55.0, 3),
                     backspins=np.linspace(10.0, 30.0, 2),
                     n_speed=40, v_lo=6.0, v_hi=10.0)
        if p3.read_bytes().decode() == p4.read_bytes().decode():
            ok += 1
            print("  [OK] 2D run_sweep_2d: CSV 逐字节一致")
        else:
            print("  [XX] 2D run_sweep_2d: CSV 不一致")
        expected_keys = {"made", "swish", "bank_in", "rattle_in",
                         "hit_board", "hit_edge", "edge_ct", "plane_h"}
        keys = set(batch_simulate_2d(2.0, 51.0, 23.0, 7.9,
                                     FREE_THROW_2D).keys())
        if expected_keys <= keys:
            ok += 1
            print("  [OK] batch_simulate_2d 返回预期结果字段")
        else:
            print(f"  [XX] 缺少结果字段: {expected_keys - keys}")
        print(f"\n自检 {ok}/3 通过 (临时目录 {out_dir})")
        temp_dir.cleanup()
        sys.exit(0 if ok == 3 else 1)

    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "both"
    if arg in ("--mp", "-mp", "mp"):
        # 3D 多进程并行扫描（仅在网格规模很大时才有必要；默认单进程摊平版已足够快）
        run_sweep_mp()
    elif arg == "free":
        run_free_throw_sweep()
    elif arg == "three":
        run_three_point_sweep()
    elif arg in ("2d", "two-d", "windows"):
        print("--- 2D 得分窗口扫描 ---")
        run_free_throw_sweep_2d()
        print()
        run_three_point_sweep_2d()
    else:
        print("--- 3D 主流程（physics.py 上半部分常数）---")
        run_free_throw_sweep()
        run_three_point_sweep()
        print("\n--- 2D（与交互器同源模型，*_2D 常数）---")
        run_free_throw_sweep_2d()
        print()
        run_three_point_sweep_2d()
