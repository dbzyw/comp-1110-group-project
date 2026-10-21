"""
simulation.py — 完整投篮模拟循环: RK4 积分 + 碰撞检测 + 得分判定 + 轨迹导出。

把 physics.py 的 RK4 积分器与 collision.py 的碰撞检测串起来:
    每一帧先积分得到新位置, 立刻做碰撞检测; 若发生碰撞就更新速度;
    若球落地 (y <= 0) 或穿过篮筐 (判定得分) 就停止。

得分规则:
    Swish    (空心)   : 从未碰筐/篮板, 球心向下穿过 y = 3.05 m 平面时
                        水平落在筐洞内。
    Rim-in   (弹框进) : 只碰过篮筐(未碰篮板), 之后最终向下穿过筐洞。
    Board-in (打板进) : 碰过篮板(可能也碰过筐), 之后最终向下穿过筐洞。
    Miss     (未进)   : 落地、出界或超时, 且从未穿过筐洞。

    与计划书 Scope 的四种结局 (swish / rim-and-in / board-and-in / miss) 对齐:
    用 has_hit_rim / has_hit_board 两个状态标记细分 —— 碰过篮板归 board-in,
    仅碰过筐归 rim-in, 都没碰归 swish。

    筐洞半径 = 篮筐半径 0.225 m 减去球半径 0.12 m = 0.105 m (球有体积,
    球心只有落在该半径内才能“不碰筐”地干净穿过)。见下方 SCORE_RADIUS。

同一文件里还有第二套 API (下划线后缀 `_2d`)，与根目录单文件
    basketball_shot_2d.py 同源：
    * `simulate_2d(h0, angle, spin, v, dist)`：2D 交互器的逐步碰撞循环，
      板面用“本步实际穿越”触发、筐口用前后两个刚性圆点，法向 0.70 + 切向 0.85，
      结局 SWISH / BANK-IN / RATTLE-IN / 各类 miss，额外产出 `plane_h`、`peak`、
      `entry`、`contacts`（含碰前/碰后速度）与逐帧速度。
    * `fit_segments_2d(res)`：把整条 RK4 轨迹按板面碰撞与水平方向反转点切段，
      对每段做 y(x) 二次拟合（系数里携带阻力、升力与反弹）。
      两套常数不可混用：2D 质量 0.60 kg / 密度 1.204 / C_D 0.47 / 筐半径 0.2287。

坐标系与几何 (与 physics.py / collision.py 一致):
    x 从投手指向篮筐, y 向上, z 侧向; 篮板在 x = 0, 筐心在 (-0.375, 3.05, 0)。
"""

import math

import numpy as np

from physics import rk4_step, spin_vector, release_velocity, BALL_RADIUS
from collision import (
    detect_all, resolve_contacts,
    RIM_HEIGHT, RIM_RADIUS, RIM_CENTER, BACKBOARD_X,
)
# 得分半径: 球心能“不碰筐”地穿过筐洞的最大水平偏移 [m]
# = 篮筐半径 0.225 - 球半径 0.12 = 0.105
# 若想用更宽松的“球心在筐半径 0.225 m 内就算进”判据, 改为 RIM_RADIUS。
SCORE_RADIUS = RIM_RADIUS - BALL_RADIUS

# ---------------------------------------------------------------------------
# 2D 引擎的导入（与单文件同源；单独拷贝本文件时也能降级运行）
# ---------------------------------------------------------------------------
try:
    from physics import (BALL_RADIUS_2D, RIM_HEIGHT_2D, FREE_THROW_2D,
                         RELEASE_FLOOR_2D, MAGNUS_PARAM_2D, DRAG_PARAM_2D, G_2D,
                         rk4_step_2d, spin_in_plane_2d, ideal_parabola_2d,
                         vacuum_aim_2d, air_load_2d, curvature_flatten_pct_2d,
                         THREE_POINT_2D)
    from collision import (hoop_geometry_2d, bounce_off_board_2d,
                           bounce_off_rim_edge_2d, detect_scoring_cross_2d,
                           classify_outcome_2d, canonical_outcome_2d,
                           MADE_OUTCOMES_2D, MAX_BOARD_BOUNCES_2D,
                           OPENING_MARGIN_2D)
except ImportError:  # 2D 层未安装时，仍保留 3D 主流程可用
    (BALL_RADIUS_2D, RIM_HEIGHT_2D, FREE_THROW_2D, RELEASE_FLOOR_2D,
     MAGNUS_PARAM_2D, DRAG_PARAM_2D, G_2D) = (None,) * 7
    rk4_step_2d = spin_in_plane_2d = ideal_parabola_2d = vacuum_aim_2d = None
    air_load_2d = curvature_flatten_pct_2d = None
    hoop_geometry_2d = bounce_off_board_2d = bounce_off_rim_edge_2d = None
    detect_scoring_cross_2d = classify_outcome_2d = canonical_outcome_2d = None
    MADE_OUTCOMES_2D = THREE_POINT_2D = None
    MAX_BOARD_BOUNCES_2D = OPENING_MARGIN_2D = None


def save_trajectory_csv(path, times, states):
    """
    把轨迹保存为 CSV: time, x, y, z, vx, vy, vz。

    path   : 输出文件路径
    times  : np.ndarray, shape (N,)
    states : np.ndarray, shape (N, 6)  每行 [x, y, z, vx, vy, vz]
    """
    data = np.column_stack((times, states))          # (N, 7)
    header = "time,x,y,z,vx,vy,vz"
    np.savetxt(path, data, delimiter=",", header=header, comments="", fmt="%.6f")


def simulate_shot(release_pos, release_vel, backspin_rate,
                  dt: float = 1e-3, t_max: float = 4.0, max_bounces: int = 50):
    """
    模拟一次完整投篮。

    参数
    ----
    release_pos  : array_like, shape (3,)   出手点 [x, y, z] [m]
    release_vel  : array_like, shape (3,)   出手速度 [vx, vy, vz] [m/s]
    backspin_rate: float                    后旋角速度 [rad/s]
    dt           : float                    积分步长 [s]
    t_max        : float                    最大飞行时间 [s]
    max_bounces  : int                      最大碰撞次数 (防死循环)

    返回 dict:
        outcome      : "swish" | "rim-in" | "board-in" | "miss"
        reason       : 结束原因描述
        contacted    : 是否碰过筐/篮板 (has_hit_rim or has_hit_board)
        has_hit_rim  : 是否真正弹到过篮筐
        has_hit_board: 是否真正弹到过篮板
        contacts     : 碰撞类型序列 (["rim", "backboard", ...], 按发生顺序)
        times        : np.ndarray (N,)
        states       : np.ndarray (N, 6)  每行 [x, y, z, vx, vy, vz]
    """
    # 输入校验与隧穿保护: dt 过大时球可能单步穿过篮筐
    # (碰撞管道直径约 0.24 m; 在 dt=2e-3 下需 >120 m/s 才会隧穿, 篮球远达不到)
    if dt > 2e-3:
        raise ValueError(f"dt = {dt} 过大, 可能发生隧穿 (建议 dt <= 2e-3)")

    release_pos = np.asarray(release_pos, dtype=float)
    if release_pos[1] < 0.0:
        raise ValueError(f"出手点 y = {release_pos[1]:.3f} < 0, 球不能在地面以下")

    omega = spin_vector(backspin_rate)

    state = np.empty(6, dtype=float)
    state[0:3] = release_pos
    state[3:6] = np.asarray(release_vel, dtype=float)

    times = [0.0]
    states = [state.copy()]

    contacts = []          # 碰撞类型序列 (按发生顺序)
    has_hit_rim = False    # 是否真正弹到过篮筐
    has_hit_board = False  # 是否真正弹到过篮板
    bounce_count = 0

    outcome = "miss"
    reason = ""

    t = 0.0
    while t < t_max:
        prev = state
        state = rk4_step(state, dt, omega)
        t += dt

        # 1) 落地: 球心 y <= 0 (插值到恰好 y = 0)
        if state[1] <= 0.0:
            y_prev = prev[1]
            frac = y_prev / (y_prev - state[1])
            land = prev + frac * (state - prev)
            times.append((t - dt) + frac * dt)
            states.append(land)
            outcome = "miss"
            reason = "hit floor"
            break

        # 2) 得分: 向下穿过筐面 (y = 3.05) 且水平落在筐洞内
        if prev[1] > RIM_HEIGHT and state[1] <= RIM_HEIGHT:
            frac = (prev[1] - RIM_HEIGHT) / (prev[1] - state[1])
            xc = prev[0] + frac * (state[0] - prev[0])
            zc = prev[2] + frac * (state[2] - prev[2])
            h = math.hypot(xc - RIM_CENTER[0], zc - RIM_CENTER[2])
            if h <= SCORE_RADIUS:
                cross = prev + frac * (state - prev)   # 精确筐面交点
                times.append((t - dt) + frac * dt)
                states.append(cross)
                if not has_hit_rim and not has_hit_board:
                    outcome = "swish"
                elif has_hit_board:
                    outcome = "board-in"          # 碰过篮板 (可能也碰筐)
                else:
                    outcome = "rim-in"            # 仅碰过篮筐
                reason = f"through hoop at horizontal r = {h:.3f} m"
                break

        # 3) 碰撞检测与响应 (篮板/篮筐)
        collisions = detect_all(state[0:3])
        if collisions:
            # Record all incoming contacts before resolving their combined effect.
            incoming_kinds = [
                col.kind for col in collisions
                if float(np.dot(state[3:6], col.normal)) < 0.0
            ]
            state[0:3], state[3:6] = resolve_contacts(
                state[0:3], state[3:6], collisions
            )
            if incoming_kinds:
                has_hit_board |= "backboard" in incoming_kinds
                has_hit_rim |= "rim" in incoming_kinds
                contacts.extend(incoming_kinds)
                bounce_count += len(incoming_kinds)

        # 4) 记录本帧
        times.append(t)
        states.append(state.copy())

        # 5) 出界 / 异常终止
        if state[0] > BACKBOARD_X + 0.5:
            outcome = "miss"
            reason = "passed behind backboard"
            break
        if bounce_count > max_bounces:
            outcome = "miss"
            reason = "too many bounces"
            break

    if outcome == "miss" and not reason:
        reason = "timeout (t_max reached)"

    return {
        "outcome": outcome,
        "reason": reason,
        "contacted": has_hit_rim or has_hit_board,
        "has_hit_rim": has_hit_rim,
        "has_hit_board": has_hit_board,
        "contacts": contacts,
        "times": np.asarray(times),
        "states": np.asarray(states),
    }


# ===========================================================================
# 2D 单发模拟 (basketball_shot_2d.py 同源)
# ===========================================================================
# 逐步顺序与单文件的 `simulate` 完全一致：
#   RK4 推一步 -> 更新 peak -> 记录首次穿筐面高度 plane_h -> 板面穿越反弹
#   -> 前后缘两次单独的筐沿反弹 -> 穿筐得分判定 -> 落地判定 -> 记录并推进。
# 只要保持这个顺序，本库与单文件 UI 在任何参数下给出逐位一致的结果
# (test_core.py 里有直接对比它们的重现测试)。

def simulate_2d(h0: float, angle_deg: float, spin: float, v: float, dist: float,
                *, air: bool = True, max_t: float = 4.0, dt: float = 1e-3,
                max_board_bounces: int = MAX_BOARD_BOUNCES_2D,
                opening_margin: float = OPENING_MARGIN_2D):
    """
    2D 单发投篮：定步长 RK4 + 板面/前后缘碰撞循环 + 穿筐得分判定。

    参数
    ----
    h0        : 出手高度 (球心离地) [m]
    angle_deg : 出手仰角 [deg]，后旋在飞行平面内的分量 = spin·sin(θ)
    spin      : 后旋角速率 [rad/s]
    v         : 出手速率 [m/s]
    dist      : 出手点到筐心的水平距离 [m]（4.60=罚球，6.75=三分）
    air       : False 时关闭阻力与马格努斯升力（退化为理想抛体）
    max_t, dt : 最长飞行时间与积分步长
    max_board_bounces : 板面反弹上限（防死循环）
    opening_margin      : 筐口内沿两侧余量 [m]（默认 12 mm）

    返回 dict（键与单文件的 `simulate` 同构，额外多了 VX/VY）：
        T/X/Y/VX/VY  : 逐帧时间、位置与速度（numpy 数组）
        outcome      : "SWISH"/"BANK-IN"/"RATTLE-IN" 或具体 miss 描述
        made         : bool
        entry        : 入筐角 [deg]，未进为 None
        plane_h      : 球心首次到达 x = dist 时的高度 [m]（供“短/长”判据）
        peak         : 最高点 [m]
        board/hits   : 是否碰过板 / 板面反弹次数
        edge         : 筐沿反弹次数
        xF/xB/xbc    : 前缘、后缘与板参考面坐标 [m]
        flight       : 飞行时间 [s]
        air          : 本发是否开启空气
        contacts     : 碰撞记录列表（kind/t/x/y/tin/tout，板面额外有 face，
                       筐沿额外有 edge）
    """
    th = math.radians(angle_deg)
    wz = spin * math.sin(th)
    xF, xB, xbc = hoop_geometry_2d(dist)

    s = np.array([0.0, h0, v * math.cos(th), v * math.sin(th)])
    T = [0.0]; X = [s[0]]; Y = [s[1]]; VX = [s[2]]; VY = [s[3]]
    t = 0.0
    board = False; hits = 0; edge = 0
    outcome = "in flight"; entry = None; plane_h = None; peak = h0
    contacts = []

    def record(sx, sy, svx, svy):
        T.append(t); X.append(float(sx)); Y.append(float(sy))
        VX.append(float(svx)); VY.append(float(svy))

    for _ in range(int(max_t / dt)):
        s2 = rk4_step_2d(s, dt, wz, air=air)

        if s2[1] > peak:
            peak = float(s2[1])

        # 首次穿过筐所在竖直平面时的高度（线性插值）
        if plane_h is None and s[0] < dist <= s2[0]:
            w = (dist - s[0]) / (s2[0] - s[0])
            plane_h = float(s[1] + w * (s2[1] - s[1]))

        # 篮板：只在球心本步实际穿越板面且接触高度落在板面窗口内才触发，
        # 所以擦板而过会继续飞到板后而不是“瞬移”回板上
        if hits < max_board_bounces:
            out = bounce_off_board_2d(s, s2, xbc, t + dt)
            if out is not None:
                s2, ct = out
                hits += 1
                board = True
                contacts.append(ct)

        # 筐沿前后两个端点（视为刚性圆点）
        for xe in (xF, xB):
            out = bounce_off_rim_edge_2d(s2, xe, t + dt)
            if out is not None:
                s2, ct = out
                edge += 1
                contacts.append(ct)

        # 球心向下穿过筐口
        score = detect_scoring_cross_2d(s, s2, xF, xB,
                                        opening_margin=opening_margin)
        if score is not None:
            entry = float(score["entry_deg"])
            outcome = classify_outcome_2d(board, edge != 0)
            t += dt
            record(s2[0], s2[1], s2[2], s2[3])
            break

        # 落地（球心降到 0.10 m 以下）-> 按当时的状态细分死法
        if s2[1] < RELEASE_FLOOR_2D:
            if board:
                outcome = "off the board, out"
            elif edge:
                outcome = "off the rim, out"
            elif max(X) > xbc + 0.02:
                outcome = "past the board, lands behind"
            elif plane_h is not None and plane_h < RIM_HEIGHT_2D:
                outcome = "long miss, past the hoop"
            elif plane_h is not None:
                outcome = "short, low at the rim plane"
            else:
                outcome = "well short"
            t += dt
            record(s2[0], s2[1], s2[2], s2[3])
            break

        t += dt
        record(s2[0], s2[1], s2[2], s2[3])
        s = s2

    made = outcome in MADE_OUTCOMES_2D
    return dict(T=np.array(T), X=np.array(X), Y=np.array(Y),
                VX=np.array(VX), VY=np.array(VY), outcome=outcome,
                made=made, entry=entry, plane_h=plane_h, peak=peak,
                board=board, hits=hits, edge=edge, xF=xF, xB=xB, xbc=xbc,
                flight=t, air=air, contacts=contacts)


def fit_segments_2d(res):
    """
    把整条 2D RK4 轨迹切成若干“在 x 上单值”的段落，对每段做 y(x) 二次拟合。

    切点：出手、每次**板面**碰撞、以及每个水平方向反转点（板/筐反弹后
    反向飞行），保证每段 x 单调，拟合才有意义；反向段会被翻转后再拟合。
    因此每段二次系数里“编码”了空气阻力、马格努斯升力和全部反弹，
    UI 里的青色弧线和读出面板的“轨迹函数”就是它（与单文件的 `fit_segments` 同构）。

    返回按时间顺序的段落列表，每段 dict：
        a2, a1, a0   : y = a2*x^2 + a1*x + a0
        x0, x1       : 适用区间 [m]
        after        : 是否属于反弹之后的分支
    """
    T, X, Y = res["T"], res["X"], res["Y"]
    cuts = [T[0]] + [c["t"] for c in res["contacts"] if c["kind"] == "board"] + [T[-1]]
    sgn = np.sign(np.diff(X))
    ch = np.where(np.diff(sgn) != 0)[0]
    cuts += [float(T[k + 1]) for k in ch if sgn[k] != 0 and sgn[k + 1] != 0]
    cuts = sorted(set(cuts))

    segs = []
    for i in range(len(cuts) - 1):
        m = (T >= cuts[i] - 1e-9) & (T <= cuts[i + 1] + 1e-9)
        if m.sum() < 10:
            continue
        xs, ys = X[m], Y[m]
        # 每段现在在 x 上单调；若反向则翻转让拟合沿前进方向跑
        if xs[-1] < xs[0]:
            xs, ys = xs[::-1], ys[::-1]
        a2, a1, a0 = np.polyfit(xs, ys, 2)
        segs.append(dict(a2=float(a2), a1=float(a1), a0=float(a0),
                         x0=float(xs[0]), x1=float(xs[-1]),
                         after=bool(cuts[i] > 0.001)))
    return segs


def save_2d_csv(path, res):
    """
    把 2D 模拟保存为 CSV：`time,x,y,vx,vy`（列为单文件本身只存了位置，
    本库额外存了速度，便于事后算入筐角与空气负荷）。
    """
    data = np.column_stack((res["T"], res["X"], res["Y"], res["VX"], res["VY"]))
    np.savetxt(path, data, delimiter=",",
               header="time,x,y,vx,vy", comments="", fmt="%.6f")


def readout_2d(res, h0: float, angle_deg: float, spin: float, v: float,
               dist: float):
    """
    把一次 2D 模拟整理成可读指标 dict（与 UI 读出面板同源的计算）。

    键：outcome / canonical（归一化到 swish|board-in|rim-in|miss）/ made /
    hang_time / entry_angle / apex / apex_vs_rim / plane_h / cm_below_rim /
    board_hits / rim_hits / segments（逐段二次拟合）；开启空气时额外给
    launch_drag_ms2、launch_drag_pct_g、launch_magnus_ms2、launch_magnus_pct_g、
    omega_z、vacuum_min_speed、speed_cost_pct，以及 flatten_pct
    （拟合弧比同参真空抛物线平缓的百分比，来自阻力 + 马格努斯升力）。
    """
    segs = fit_segments_2d(res)
    board_ct = [c for c in res["contacts"] if c["kind"] == "board"]
    out = dict(outcome=res["outcome"], canonical=canonical_outcome_2d(res["outcome"]),
               made=res["made"], hang_time=float(res["T"][-1]),
               entry_angle=res["entry"], apex=float(res["peak"]),
               apex_vs_rim=float(res["peak"] - RIM_HEIGHT_2D),
               board_hits=len(board_ct), rim_hits=int(res["edge"]),
               plane_h=res["plane_h"], segments=segs)
    out["cm_below_rim"] = ((RIM_HEIGHT_2D - res["plane_h"]) * 100.0
                           if res["plane_h"] is not None else None)
    if res["air"]:
        drag, magnus, wz = air_load_2d(v, spin, angle_deg)
        out["omega_z"] = wz
        out["launch_drag_ms2"] = drag
        out["launch_drag_pct_g"] = drag / G_2D * 100.0
        out["launch_magnus_ms2"] = magnus
        out["launch_magnus_pct_g"] = magnus / G_2D * 100.0
        ref = vacuum_aim_2d(h0, angle_deg, dist)
        if ref:
            out["vacuum_min_speed"] = ref[0]
            out["speed_cost_pct"] = (v - ref[0]) / ref[0] * 100.0
    if segs:
        out["flatten_pct"] = curvature_flatten_pct_2d(h0, angle_deg, v, segs[0]["a2"])
    return out


# ---------------------------------------------------------------------------
# 测试: 一次标准罚球
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    FREE_THROW_DISTANCE = 4.57   # 罚球线到篮板距离 [m] (NBA)
    RELEASE_HEIGHT = 2.0         # 出手高度 [m]
    SPEED = 7.5                  # 出手速率 [m/s]
    ANGLE_DEG = 51.0             # 出手仰角 [deg]
    BACKSPIN = 23.0              # 后旋 [rad/s]

    release_pos = np.array([-FREE_THROW_DISTANCE, RELEASE_HEIGHT, 0.0])
    v0 = release_velocity(SPEED, ANGLE_DEG)

    res = simulate_shot(release_pos, v0, BACKSPIN)

    print("=" * 60)
    print("标准罚球模拟")
    print("=" * 60)
    print(f"出手点   : {release_pos} m  (距篮板 {FREE_THROW_DISTANCE} m, 高 {RELEASE_HEIGHT} m)")
    print(f"出手速度 : {np.round(v0, 3)} m/s  (速率 {SPEED} m/s, 仰角 {ANGLE_DEG}°)")
    print(f"后旋     : {BACKSPIN} rad/s")
    print("-" * 60)
    print(f"结果     : {res['outcome']}")
    print(f"原因     : {res['reason']}")
    print(f"是否碰筐/篮板: {res['contacted']}   碰撞序列 = {res['contacts']}")
    print(f"飞行时间 : {res['times'][-1]:.3f} s   轨迹点数 = {len(res['times'])}")
    print(f"末点     : 位置={np.round(res['states'][-1, 0:3], 3)} m, "
          f"速度={np.round(res['states'][-1, 3:6], 3)} m/s")

    out_csv = "trajectory.csv"
    save_trajectory_csv(out_csv, res["times"], res["states"])
    print("-" * 60)
    print(f"轨迹已保存到 {out_csv}  (列: time,x,y,z,vx,vy,vz)")

    # =====================================================================
    # 2D 模拟：与单文件交互器的 6 个典型场景对齐（DEMO_SCENES）
    # =====================================================================
    print("\n" + "=" * 70)
    print("2D 模拟器自检（与 basketball_shot_2d.py 同源，库版 2D 引擎）")
    print("=" * 70)
    scenes = [
        ("01_free_throw_swish",  2.00, 51.0, 23.0, 7.90, FREE_THROW_2D, True,  "SWISH"),
        ("02_bank_shot",         2.00, 36.0, 23.0, 9.10, FREE_THROW_2D, True,  "BANK-IN"),
        ("03_rattle_in",         2.00, 36.0, 23.0, 8.70, FREE_THROW_2D, True,  "RATTLE-IN"),
        ("04_short_miss",        2.00, 51.0, 23.0, 6.00, FREE_THROW_2D, True,  "well short"),
        ("05_air_off",           2.00, 51.0, 23.0, 7.90, FREE_THROW_2D, False, "BANK-IN"),
        ("06_three_pointer",     2.00, 45.0, 23.0, 9.46, THREE_POINT_2D,      True,  "SWISH"),
    ]
    print(f"{'scene':<20}{'outcome':<24}{'expected':<12}{'entry':>9}{'apex':>9}{'board/rim':>11}")
    ok = 0
    for name, h0, ang, spin, v, dist, air, expect in scenes:
        r2 = simulate_2d(h0, ang, spin, v, dist, air=air)
        ro = readout_2d(r2, h0, ang, spin, v, dist)
        match = (r2["outcome"] == expect)
        ok += match
        entry = f"{r2['entry']:.1f}" if r2["entry"] is not None else "n/a"
        collide = f"{ro['board_hits']}/{ro['rim_hits']}"
        print(f"{name:<20}{r2['outcome']:<24}{expect:<12}{entry:>9}"
              f"{r2['peak']:>9.2f}{collide:>11}  {'OK' if match else 'DIVERGE'}")
    print(f"\n\u573a\u666f\u590d\u73b0: {ok}/{len(scenes)} \u4e0e SIMULATION_2D_DEMOS.md \u4e00\u81f4")

    r2 = simulate_2d(2.00, 51.0, 23.0, 7.90, FREE_THROW_2D)
    ro = readout_2d(r2, 2.00, 51.0, 23.0, 7.90, FREE_THROW_2D)
    out_2d = "trajectory_2d.csv"
    save_2d_csv(out_2d, r2)
    print(f"\n罚球基准场景 2.00 m / 51° / 23 rad/s / 7.90 m/s / 4.60 m:")
    print(f"  结局       = {r2['outcome']}   (归一化 = {ro['canonical']})")
    print(f"  hang time  = {ro['hang_time']:.2f} s   入筐角 = {ro['entry_angle']:.1f}°")
    print(f"  最高点     = {ro['apex']:.2f} m ({ro['apex_vs_rim']:+.2f} vs 筐沿)")
    print(f"  到筐面     {ro['cm_below_rim']:.0f} cm 低于筐沿"
          if ro["cm_below_rim"] is not None and ro["cm_below_rim"] > 2
          else f"  到筐面     与筐沿齐平")
    print(f"  碰撞       板 {ro['board_hits']} / 筐 {ro['rim_hits']}")
    if "launch_drag_pct_g" in ro:
        print(f"  启动阻力   {ro['launch_drag_ms2']:.2f} m/s^2 ({ro['launch_drag_pct_g']:.0f}% g)   "
              f"升力 {ro['launch_magnus_ms2']:.2f} ({ro['launch_magnus_pct_g']:.0f}% g)")
        print(f"  真空最小   {ro['vacuum_min_speed']:.2f} m/s   本发贵 {ro['speed_cost_pct']:+.1f}%")
    segs = ro["segments"]
    print(f"  拟合分支   {len(segs)} 段")
    for i, sg in enumerate(segs[:3]):
        print(f"    分支 {i + 1}: y = {sg['a2']:.4f}x^2 {sg['a1']:+.3f}x {sg['a0']:+.2f} "
              f" on {sg['x0']:.2f} ≤ x ≤ {sg['x1']:.2f}"
              + ("  (碰撞后分支)" if sg["after"] else "  (出手到首次碰撞)"))
    if ro.get("flatten_pct") is not None:
        f_pct = ro["flatten_pct"]
        verb = "平缓" if f_pct >= 0 else "陡"
        print(f"  y(x) 曲率比同参真空抛物线{verb} {abs(f_pct):.0f}%（与单文件 UI 同一个公式："
              f"(|a2_ideal|-|a2_fit|)/|a2_ideal|；阻力会拉平 x 方向而抬高 |a2|）")
    print(f"轨迹已保存到 {out_2d}  (列: time,x,y,vx,vy)")
