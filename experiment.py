"""
experiment.py — 向量化参数扫描: 出手角度 × 后旋速率 → 命中概率, 输出 data.csv / data_three.csv。

优化要点:
    * 把整个 (角度 × 后旋 × 抖动) 网格一次性摊平成 (N, 6) 状态矩阵,
      用 numpy 向量化的 RK4 (rk4_step_batch) + 向量化碰撞检测
      (detect_*_batch) 单批并行推进, 替代原先“289 个格子各跑一个 Python 循环”。
    * 提供 run_sweep (单进程, 默认) 与 run_sweep_mp (多进程, 可选)。

用法:
    python experiment.py               # 罚球 + 三分球两个扫描
    python experiment.py free          # 只跑罚球扫描 -> data.csv
    python experiment.py three         # 只跑三分球扫描 -> data_three.csv
    python experiment.py --mp          # 罚球扫描, 多进程并行
    (列: angle, backspin, p_make[, p_swish, p_rim_in, p_board_in])
"""

import os
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from physics import rk4_step_batch, BALL_RADIUS
from collision import (
    detect_backboard_batch, detect_rim_batch, RESTITUTION,
    RIM_HEIGHT, RIM_RADIUS, RIM_CENTER, BACKBOARD_X,
)

# ---------------------------------------------------------------------------
# 出手条件 (标准罚球)
# ---------------------------------------------------------------------------
RELEASE_POS = np.array([-4.57, 2.0, 0.0])
RELEASE_SPEED = 7.5

# ---------------------------------------------------------------------------
# 出手条件: 三分球 (FIBA 三分线距筐心 6.75 m; 速率更高以覆盖更长射程)
# ---------------------------------------------------------------------------
THREE_DIST = 6.75
THREE_RELEASE_POS = np.array([RIM_CENTER[0] - THREE_DIST, 2.0, 0.0])  # (-7.125, 2.0, 0)
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


def release_velocity_batch(speeds, angles_deg):
    """由速率/仰角数组构造出手速度向量组 (N, 3)。"""
    ang = np.deg2rad(angles_deg)
    return np.column_stack([speeds * np.cos(ang), speeds * np.sin(ang),
                            np.zeros_like(speeds)])


def batch_simulate(positions, velocities, backspin_rate):
    """
    批量模拟 N 次投篮 (可不同后旋)。

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

    n_shots = positions.shape[0]
    omega = np.zeros((n_shots, 3))                         # 每球一份自旋向量
    omega[:, 2] = np.broadcast_to(np.asarray(backspin_rate, dtype=float), (n_shots,))

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
                       P_swish=None, P_rim=None, P_board=None):
    """
    把命中率网格写成 CSV: 先写临时文件, 再用 os.replace 原子替换。

    这样即使中途失败也不会留下半截损坏文件; 目录不存在时给出清晰报错。

    若传入 P_swish / P_rim / P_board, 会额外写出 p_swish / p_rim_in / p_board_in 三列。
    """
    out_path = Path(out_csv)
    parent = out_path.parent
    if not parent.is_dir():
        raise FileNotFoundError(f"输出目录不存在: {parent}")

    with_breakdown = P_swish is not None and P_rim is not None and P_board is not None
    header = "angle,backspin,p_make"
    if with_breakdown:
        header += ",p_swish,p_rim_in,p_board_in"
    lines = [header + "\n"]
    for i, ang in enumerate(angles):
        for j, back in enumerate(backspins):
            row = f"{ang:.4f},{back:.4f},{P[i, j]:.6f}"
            if with_breakdown:
                row += (f",{P_swish[i, j]:.6f},{P_rim[i, j]:.6f},"
                        f"{P_board[i, j]:.6f}")
            lines.append(row + "\n")

    fd, tmp = tempfile.mkstemp(dir=str(parent), suffix=".csv.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.writelines(lines)
        os.replace(tmp, out_path)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError(f"写入 {out_csv} 失败: {e}") from e


def run_sweep(out_csv="data.csv", seed=0, release_pos=RELEASE_POS, speed=RELEASE_SPEED,
              angles_deg=ANGLES_DEG, backspins=BACKSPINS):
    """
    单次摊平 (角度 × 后旋 × 抖动) 网格, 单批向量化模拟全部出手, 统计命中率。

    相比原先的嵌套循环: 消除了 N 次 Python while 循环与大量小数组的
    numpy 调用开销, 全部出手拼成一个 (N, 6) 状态矩阵一次跑完。

    release_pos / speed / angles_deg / backspins 可覆盖, 用于罚球与三分球扫描。
    """
    angles_deg = np.asarray(angles_deg, dtype=float)
    backspins = np.asarray(backspins, dtype=float)
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

    _write_grid_atomic(angles_deg, backspins, P, out_csv,
                       P_swish=P_swish, P_rim=P_rim, P_board=P_board)

    i_peak, j_peak = np.unravel_index(np.argmax(P), P.shape)
    print(f"完成: {n_ang}×{n_back} 个格子 × {n_shots} 次出手 = {ang_tile.size} 次, "
          f"用时 {elapsed:.1f}s, 已保存 {out_csv}")
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
    angles_deg = np.asarray(angles_deg, dtype=float)
    backspins = np.asarray(backspins, dtype=float)
    workers = workers or os.cpu_count() or 1
    child_seeds = np.random.default_rng(seed).integers(0, 2**31 - 1, len(backspins))

    tasks = [(b, s, release_pos, speed, angles_deg) for b, s in zip(backspins, child_seeds)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        cols = list(ex.map(_simulate_backspin_block, tasks))

    P = np.column_stack(cols)          # (n_ang, n_back)
    _write_grid_atomic(angles_deg, backspins, P, out_csv)
    print(f"完成: 多进程 ({workers} workers) 扫描, 已保存 {out_csv}")
    return P


def run_free_throw_sweep(out_csv="data.csv", seed=0):
    """罚球扫描 (默认网格)。"""
    return run_sweep(out_csv, seed, RELEASE_POS, RELEASE_SPEED, ANGLES_DEG, BACKSPINS)


def run_three_point_sweep(out_csv="data_three.csv", seed=0):
    """三分球扫描 (FIBA 6.75 m, 更窄角度窗口)。"""
    return run_sweep(out_csv, seed, THREE_RELEASE_POS, THREE_SPEED,
                     THREE_ANGLES_DEG, THREE_BACKSPINS)


if __name__ == "__main__":
    import sys

    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "both"
    if arg in ("--mp", "-mp", "mp"):
        # 多进程并行扫描 (仅在网格规模很大时才有必要; 默认单进程摊平版已足够快)
        run_sweep_mp()
    elif arg == "free":
        run_free_throw_sweep()
    elif arg == "three":
        run_three_point_sweep()
    else:
        run_free_throw_sweep()
        run_three_point_sweep()
