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
