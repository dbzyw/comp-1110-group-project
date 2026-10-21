"""
physics.py — 篮球飞行刚体动力学与 RK4 积分核心
(纯物理投篮模拟, COMP1110 小组项目)

坐标系 (右手系, 全程 SI 单位):
    x -> 水平, 从投手指向篮筐 (前进方向)
    y -> 竖直, 向上为正
    z -> 水平, 侧向 (与 x, y 构成右手系)

建模的三个力 (与项目计划书一致):
    1. 重力            F_g = (0, -m*g, 0)
    2. 二次空气阻力     F_d = - 1/2 * rho * C_d * A * |v| * v
    3. 马格努斯升力     F_M = 1/2 * rho * A * C_L0 * R * (omega × v)

    马格努斯项等价于“升力系数”形式
        F_M = 1/2 * rho * C_L * A * |v|^2 * (omega_hat × v_hat)
    其中升力系数取 C_L = C_L0 * (R*|omega| / |v|), 即与自旋参数
    S = R*|omega|/|v| 成正比。代入后化简为上面的叉积形式, 对自旋向量
    和速度均线性, 因此“后旋越快, 升力越大”。

    纯后旋时自旋向量为 omega = (0, 0, +omega_rate):
    对于向前上方的速度, omega × v 的 y 分量为正, 产生向上升力,
    符合物理直觉。

状态向量 (6 维):
    state = [x, y, z, vx, vy, vz]

飞行过程中自旋保持恒定 (无自旋衰减), 符合项目范围界定。

===========================================================================
同一文件里的两套 API (两套常数故意不同, 结论不可互相搬运)
===========================================================================
  3D 主流程 (本文件上半部分, 正式实验 / 参数扫描 / 验证链路使用):
      G = 9.81, RHO_AIR = 1.225, C_D = 0.50, C_L0 = 1.00 (升力系数随自旋参数
      S = R|omega|/|v| 变化), BALL_MASS = 0.624 kg, BALL_RADIUS = 0.12 m,
      篮筐半径 0.225 m, 碰撞用单一法向恢复系数 e = 0.70

  2D 模拟器 (本文件下半部分, 所有 *_2D 符号; 与根目录单文件交互器
      basketball_shot_2d.py 同源、常数冻结自课程 deck):
      G_2D = 9.81 (同 G), RHO_AIR_2D = 1.204, C_D_2D = 0.47, C_L_2D = 0.20 (固定升力
      系数), BALL_MASS_2D = 0.60 kg, 篮筐半径 RIM_RADIUS_2D = 0.2287 m
      (45.7 cm 内径), 筐后沿到板面 0.15 m, 罚球 4.60 m / 三分 6.75 m,
      碰撞法向恢复 0.70 + 切向恢复 0.85

两套互不干扰, 2D 符号全部带 `_2D` 后缀。报告里引用任何数值必须注明出处
是哪一套模型 (见 README 的 ⚠️ 说明与 SIMULATION_2D_PHYSICS.md §7)。
"""

import math

import numpy as np

# ---------------------------------------------------------------------------
# 物理常数 (所有 3D 实验统一冻结 — 见计划书“常数冻结”要求)
# ---------------------------------------------------------------------------
G           = 9.81          # 重力加速度                      [m/s^2]
RHO_AIR     = 1.225         # 空气密度 (海平面)               [kg/m^3]
C_D         = 0.50          # 球的阻力系数 (光滑球体 ~0.47-0.50)   [-]
C_L0        = 1.00          # 马格努斯系数 (无量纲, 冻结)          [-]
# 说明: 升力系数 C_L = C_L0 * (R*|omega|/|v|)。取 C_L0 = 1.0 时,
# 典型罚球 (23 rad/s, 7 m/s) 下 C_L ≈ 0.39, 落在旋转球体升力系数的
# 文献范围 (~0.2-0.4) 内。所有常数一经设定即冻结, 不随扫描结果调整。
# 2D 模拟器另有一套冻结常数, 见文件下半部分 (*_2D 后缀), 两者不可混用。
BALL_MASS   = 0.624         # 标准篮球质量                    [kg]
BALL_RADIUS = 0.12          # 篮球半径 (周长约 0.75 m)         [m]
# 注: 3D 主流程的篮筐半径是 0.225 m (collision.py RIM_RADIUS);
#     2D 模拟器用 0.2287 m (RIM_RADIUS_2D, deck 冻结的 45.7 cm 内径)。

# 迎风截面积
BALL_AREA = np.pi * BALL_RADIUS ** 2   # [m^2]

# 重力作为力向量 (质量 × 重力场)
_GRAVITY_FORCE = np.array([0.0, -G * BALL_MASS, 0.0])


# ---------------------------------------------------------------------------
# 力
# ---------------------------------------------------------------------------
def gravity_force() -> np.ndarray:
    """恒定的向下重力向量 [N]。"""
    return _GRAVITY_FORCE.copy()


def drag_force(v: np.ndarray) -> np.ndarray:
    """
    二次空气阻力 [N], 方向与速度相反, 大小与 |v|^2 成正比。

        F_d = - 1/2 * rho * C_d * A * |v| * v
    """
    speed = float(np.linalg.norm(v))
    if speed == 0.0:
        return np.zeros(3)
    return -0.5 * RHO_AIR * C_D * BALL_AREA * speed * v


def magnus_force(v: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """
    由自旋引起的马格努斯升力 [N]。

        F_M = 1/2 * rho * A * C_L0 * R * (omega × v)
    """
    return 0.5 * RHO_AIR * BALL_AREA * C_L0 * BALL_RADIUS * np.cross(omega, v)


def acceleration(v: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """由 重力 + 阻力 + 马格努斯力 得到的合加速度 [m/s^2]。"""
    force = gravity_force() + drag_force(v) + magnus_force(v, omega)
    return force / BALL_MASS


# ---------------------------------------------------------------------------
# 常微分方程右端 与 RK4 积分器
# ---------------------------------------------------------------------------
def derivatives(state: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """
    6 维状态向量的时间导数。

        state = [x, y, z, vx, vy, vz]
        返回  = [vx, vy, vz, ax, ay, az]
    """
    v = state[3:6]
    a = acceleration(v, omega)
    return np.concatenate([v, a])


def rk4_step(state: np.ndarray, dt: float, omega: np.ndarray) -> np.ndarray:
    """用经典四阶 Runge-Kutta 方法推进一个时间步 dt。"""
    k1 = derivatives(state, omega)
    k2 = derivatives(state + 0.5 * dt * k1, omega)
    k3 = derivatives(state + 0.5 * dt * k2, omega)
    k4 = derivatives(state + dt * k3, omega)
    return state + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def acceleration_batch(v: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """
    向量化版 acceleration: 一次计算 N 个球的合加速度。

    v     : np.ndarray, shape (N, 3)  速度向量组
    omega : np.ndarray, shape (3,) 或 (N, 3)  自旋向量

    返回 shape (N, 3) 的加速度。
    """
    v = np.asarray(v, dtype=float)
    omega = np.asarray(omega, dtype=float)
    if omega.ndim == 1:
        omega = np.broadcast_to(omega, v.shape)

    speed = np.linalg.norm(v, axis=1, keepdims=True)          # (N, 1)
    fg = np.zeros_like(v)
    fg[:, 1] = -G * BALL_MASS

    fd = -0.5 * RHO_AIR * C_D * BALL_AREA * speed * v
    fm = 0.5 * RHO_AIR * BALL_AREA * C_L0 * BALL_RADIUS * np.cross(omega, v)

    return (fg + fd + fm) / BALL_MASS


def rk4_step_batch(state: np.ndarray, dt: float, omega: np.ndarray) -> np.ndarray:
    """
    向量化版 rk4_step: 一次推进 N 个状态。

    state : np.ndarray, shape (N, 6)  每行 [x, y, z, vx, vy, vz]
    omega : np.ndarray, shape (3,) 或 (N, 3)

    返回 shape (N, 6)。
    """
    def d(s):
        v = s[:, 3:6]
        a = acceleration_batch(v, omega)
        return np.concatenate([v, a], axis=1)

    k1 = d(state)
    k2 = d(state + 0.5 * dt * k1)
    k3 = d(state + 0.5 * dt * k2)
    k4 = d(state + dt * k3)
    return state + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


# ---------------------------------------------------------------------------
# 轨迹积分
# ---------------------------------------------------------------------------
def spin_vector(backspin_rate: float) -> np.ndarray:
    """
    返回纯后旋对应的角速度向量 (rad/s)。

    正的 backspin_rate 绕 +z 轴旋转, 对向前运动的球产生向上升力。
    """
    return np.array([0.0, 0.0, float(backspin_rate)])


def integrate(release_pos, release_vel, backspin_rate,
              dt: float = 1e-3, t_max: float = 3.0, stop=None,
              stop_at_floor: bool = True):
    """
    从出手时刻积分整条轨迹, 直到落地 (y < 0)、t_max 或 stop(state) 返回 True。

    参数
    ----
    release_pos : array_like, shape (3,)
        出手点 [x, y, z], 单位米。
    release_vel : array_like, shape (3,)
        出手速度 [vx, vy, vz], 单位 m/s。
    backspin_rate : float
        后旋角速度 (rad/s), 自旋向量取 (0, 0, +rate)。
    dt : float
        积分步长 [s]。RK4 在 ~1e-3 s 下足够稳定。
    t_max : float
        最大飞行时间 [s]。
    stop : callable(state) -> bool, 可选
        额外的提前终止判据, 例如“到达篮筐所在竖直平面”。
    stop_at_floor : bool, 默认 True
        是否在球心 y < 0 (落地) 时停止, 并把落点线性插值到恰好 y = 0。

    返回
    ----
    times : np.ndarray, shape (N,)
    states : np.ndarray, shape (N, 6)
        states[i] = [x, y, z, vx, vy, vz] 为 times[i] 时刻的状态。
    """
    if dt <= 0.0:
        raise ValueError(f"dt must be positive, got {dt!r}")
    if t_max < 0.0:
        raise ValueError(f"t_max must be non-negative, got {t_max!r}")

    release_pos = np.asarray(release_pos, dtype=float)
    release_vel = np.asarray(release_vel, dtype=float)
    if release_pos.shape != (3,):
        raise ValueError(f"release_pos must have shape (3,), got {release_pos.shape}")
    if release_vel.shape != (3,):
        raise ValueError(f"release_vel must have shape (3,), got {release_vel.shape}")

    omega = spin_vector(backspin_rate)

    state = np.empty(6, dtype=float)
    state[0:3] = release_pos
    state[3:6] = release_vel

    times = [0.0]
    states = [state.copy()]

    t = 0.0
    while t < t_max:
        prev = state
        state = rk4_step(state, dt, omega)
        t += dt

        # 落地判据: 球心 y < 0 视为落地, 停止并把落点插值到恰好 y = 0
        if stop_at_floor and state[1] < 0.0:
            y_prev = prev[1]
            frac = y_prev / (y_prev - state[1])   # y = 0 处的线性插值系数
            land_state = prev + frac * (state - prev)
            land_t = (t - dt) + frac * dt
            times.append(land_t)
            states.append(land_state)
            break

        times.append(t)
        states.append(state.copy())
        if stop is not None and stop(state):
            break

    return np.asarray(times), np.asarray(states)


def release_velocity(speed: float, angle_deg: float, azimuth_deg: float = 0.0) -> np.ndarray:
    """
    由速率与仰角构造出手速度向量。

    参数
    ----
    speed       : 出手速率 [m/s]
    angle_deg   : 仰角 (相对水平面) [deg]
    azimuth_deg : 方位角, 0 表示正对篮筐, 正值为 +z 方向偏转 [deg]
    """
    if speed < 0.0:
        raise ValueError(f"speed must be non-negative, got {speed!r}")

    ang = np.deg2rad(angle_deg)
    az = np.deg2rad(azimuth_deg)
    vx = speed * np.cos(ang) * np.cos(az)
    vy = speed * np.sin(ang)
    vz = speed * np.cos(ang) * np.sin(az)
    return np.array([vx, vy, vz])


# ===========================================================================
# 2D 引擎 (basketball_shot_2d.py 同源)
# ===========================================================================
# 状态向量 4 维: [x, y, vx, vy]; 后旋只取落在飞行平面内的分量
#   omega_z = spin * sin(theta)
# 合并后的两个参数 (与单文件里的 BD / BM 完全一致):
#   BD = 0.5*rho*C_D*A/M        [1/m]    阻力项系数
#   BM = 0.5*rho*C_L*A*R/M      [-]      马格努斯项系数

BALL_RADIUS_2D   = 0.12      # 球半径                       [m]
BALL_MASS_2D     = 0.60      # 球质量 (deck 冻结值)          [kg]
RHO_AIR_2D       = 1.204     # 空气密度 @ 20 °C              [kg/m^3]
C_D_2D           = 0.47      # 阻力系数 (球体典型值)         [-]
C_L_2D           = 0.20      # 升力系数 (固定, 不随自旋参数变)
BALL_AREA_2D     = math.pi * BALL_RADIUS_2D ** 2            # [m^2]

DRAG_PARAM_2D    = 0.5 * RHO_AIR_2D * C_D_2D * BALL_AREA_2D / BALL_MASS_2D      # ≈ 0.02134 /m
MAGNUS_PARAM_2D  = 0.5 * RHO_AIR_2D * C_L_2D * BALL_AREA_2D * BALL_RADIUS_2D / BALL_MASS_2D  # ≈ 1.0895e-3

RIM_HEIGHT_2D    = 3.05      # 筐沿高度                      [m]
RIM_RADIUS_2D    = 0.2287    # 筐口半径 (内径 45.7 cm)       [m]
BOARD_OFFSET_2D  = 0.15      # 筐后沿 -> 篮板面的距离        [m]
FREE_THROW_2D    = 4.60      # 罚球线到筐心水平距离          [m]
THREE_POINT_2D   = 6.75      # 三分线到筐心水平距离          [m]
RELEASE_FLOOR_2D = 0.10      # 视为落地的球心高度            [m]

RESTITUTION_NORMAL_2D     = 0.70   # 法向恢复系数
RESTITUTION_TANGENTIAL_2D = 0.85   # 切向恢复系数 (保留 85% 切向速度)
# 2D 的重力单独命名，即使将来有人改 3D 的 G 也不会扰动 deck 冻结的 2D 结果
G_2D               = 9.81      # 重力加速度 (与 G 同值, 但两套独立)


def spin_in_plane_2d(spin_rate: float, angle_deg: float) -> float:
    """后旋在飞行平面内的分量 omega_z = spin * sin(theta) [rad/s]。"""
    return float(spin_rate) * math.sin(math.radians(float(angle_deg)))


def acceleration_2d(vx: float, vy: float, spin_z: float, air: bool = True):
    """
    2D 合加速度 (ax, ay) [m/s^2]：重力 + 二次阻力 + 马格努斯升力。

        ax = -BD*|v|*vx + BM*omega_z*vy
        ay = -g  -BD*|v|*vy - BM*omega_z*vx

    air=False 时两套空气项归零 (退化为纯抛体, 与 ideal_parabola_2d 一致)。
    """
    kd = DRAG_PARAM_2D if air else 0.0
    km = MAGNUS_PARAM_2D if air else 0.0
    speed = math.hypot(vx, vy)
    ax = -kd * speed * vx + km * spin_z * vy
    ay = -G_2D - kd * speed * vy - km * spin_z * vx
    return ax, ay


def derivatives_2d(state, spin_z: float, air: bool = True) -> np.ndarray:
    """4 维状态 [x, y, vx, vy] 的时间导数 [vx, vy, ax, ay]。"""
    vx, vy = state[2], state[3]
    ax, ay = acceleration_2d(vx, vy, spin_z, air)
    return np.array([vx, vy, ax, ay])


def rk4_step_2d(state, dt: float, spin_z: float, air: bool = True) -> np.ndarray:
    """定步长经典 RK4 推进 2D 状态一步 (与单文件里的 dv/四阶组合同序)。"""
    k1 = derivatives_2d(state, spin_z, air)
    k2 = derivatives_2d(state + 0.5 * dt * k1, spin_z, air)
    k3 = derivatives_2d(state + 0.5 * dt * k2, spin_z, air)
    k4 = derivatives_2d(state + dt * k3, spin_z, air)
    return state + dt / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def ideal_arc_coeffs_2d(h0: float, angle_deg: float, v: float):
    """
    无空气抛物线的形状系数 (slope, a2)：y = h0 + slope*x - a2*x^2。

        slope = tan(theta),  a2 = g / (2 v^2 cos^2(theta))
    """
    th = math.radians(angle_deg)
    c = math.cos(th)
    return math.tan(th), G_2D / (2.0 * v * v * c * c)


def ideal_parabola_2d(h0: float, angle_deg: float, v: float, n: int = 400):
    """
    同参数的真空抛物线 (无空气、无升力)。

    落地判据沿用单文件：球心降到 y = RELEASE_FLOOR_2D (0.10 m) 处即视为落地，
    所以射程 x_land 是解 y(x) = 0.10 的正根。

    返回 (xs, ys, slope, a2, x_land)。
    """
    slope, a2 = ideal_arc_coeffs_2d(h0, angle_deg, v)
    b = h0 - RELEASE_FLOOR_2D
    x_land = (slope + math.sqrt(slope * slope + 4.0 * a2 * b)) / (2.0 * a2)
    xs = np.linspace(0.0, x_land, n)
    return xs, h0 + slope * xs - a2 * xs * xs, slope, a2, x_land


def vacuum_aim_2d(h0: float, angle_deg: float, dist: float,
                  rim_height: float = RIM_HEIGHT_2D):
    """
    以给定仰角用真空抛物线命中 (dist, rim_height) 所需的最小出手速率。

    不可达 (该仰角下真空抛物线在筐平面仍低于筐沿) 时返回 None。
    返回 (v_min, rhs)，其中 rhs = h0 + dist*tan(theta) - rim_height [m]。
    """
    th = math.radians(angle_deg)
    rhs = h0 + dist * math.tan(th) - rim_height
    if rhs <= 0:
        return None
    v = math.sqrt(0.5 * G_2D * dist * dist / (rhs * math.cos(th) ** 2))
    return v, rhs


def air_load_2d(v: float, spin_rate: float, angle_deg: float):
    """
    出手瞬间的空气项加速度 [m/s^2]：
        drag   = BD * v^2                     (与飞行方向相反)
        magnus = BM * |omega_z| * v           (垂直于速度, 后旋时向上)
    返回 (drag, magnus, omega_z)。
    """
    wz = spin_in_plane_2d(spin_rate, angle_deg)
    return DRAG_PARAM_2D * v * v, MAGNUS_PARAM_2D * abs(wz) * v, wz


def curvature_flatten_pct_2d(h0: float, angle_deg: float, v: float,
                             fitted_a2: float) -> float | None:
    """
    拟合弧线比理想真空抛物线"平缓"的百分比：
        (|a2_ideal| - |a2_fitted|) / |a2_ideal| * 100
    阻力与马格努斯升力都会让实际弧线的曲率变小 (正值)。
    fitted_a2 太小 (< 1e-6) 时返回 None。
    """
    _, a2_i = ideal_arc_coeffs_2d(h0, angle_deg, v)
    if abs(fitted_a2) <= 1e-6:
        return None
    return (abs(a2_i) - abs(fitted_a2)) / abs(a2_i) * 100.0


# ---------------------------------------------------------------------------
# 2D model kept in its own module; the 3D pipeline remains the authoritative
# implementation for the main project code.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 一个罚球样例: 出手点高 2.0 m, 速率 7.1 m/s, 仰角 51 度, 后旋 23 rad/s
    r0 = np.array([0.0, 2.0, 0.0])
    v0 = release_velocity(7.1, 51.0)
    times, states = integrate(r0, v0, backspin_rate=23.0, t_max=2.0)

    pos = states[:, 0:3]
    vel = states[:, 3:6]

    y = pos[:, 1]
    i_apex = int(np.argmax(y))

    # 与篮筐高度 y = 3.05 m 的首次/末次相交
    above = y >= 3.05
    cross = np.where(above[1:] != above[:-1])[0]

    print(f"出手速度向量      : {np.round(v0, 3)} m/s")
    print(f"最高点高度        : {y[i_apex]:.3f} m  (t = {times[i_apex]:.3f} s)")
    if cross.size:
        print(f"首次到达 3.05 m   : t = {times[cross[0]]:.3f} s")
        print(f"末次离开 3.05 m   : t = {times[cross[-1]]:.3f} s")
    print(f"落地时间          : t = {times[-1]:.3f} s")
    print(f"落点              : x = {pos[-1, 0]:.3f} m, y = {pos[-1, 1]:.3f} m, "
          f"z = {pos[-1, 2]:.3f} m")
    print(f"落地速度          : {np.round(vel[-1], 3)} m/s")

    print("\n" + "=" * 70)
    print("2D 模拟器常数自检 (与 basketball_shot_2d.py 同源)")
    print("=" * 70)
    print(f"球质量 M_2D      = {BALL_MASS_2D} kg   "
          f"(3D 主流程用 {BALL_MASS} kg)")
    print(f"空气密度 rho_2D  = {RHO_AIR_2D}       (3D 用 {RHO_AIR})")
    print(f"C_D_2D           = {C_D_2D}            (3D 用 {C_D})")
    print(f"升力系数 C_L_2D   = {C_L_2D} (固定)     (3D 用 C_L0={C_L0} + 自旋参数形式)")
    print(f"BD_2D            = {DRAG_PARAM_2D:.5f} /m")
    print(f"BM_2D            = {MAGNUS_PARAM_2D:.6e}")
    print(f"RIM_RADIUS_2D    = {RIM_RADIUS_2D} m   (3D 用 {0.225} m)")

    # 罚球基准情形: 2.00 m / 51° / 23 rad/s / 7.90 m/s / 4.60 m
    h0, ang, spin, v, dist = 2.00, 51.0, 23.0, 7.90, FREE_THROW_2D
    drag, magnus, wz = air_load_2d(v, spin, ang)
    print(f"\n出手样例         : {h0:.2f} m / {ang:.0f}° / {spin:.0f} rad/s / "
          f"{v:.2f} m/s / {dist:.2f} m   (omega_z = {wz:.2f} rad/s)")
    print(f"启动阻力加速度    = {drag:.2f} m/s^2 ({drag / G_2D * 100:.0f}% of g)")
    print(f"启动升力加速度    = {magnus:.2f} m/s^2 ({magnus / G_2D * 100:.0f}% of g)")
    xs, ys, slope_i, a2_i, x_land = ideal_parabola_2d(h0, ang, v)
    print(f"真空抛物线        : y = {h0:.2f} + {slope_i:.3f}x - {a2_i:.4f}x^2   "
          f"(射程 {x_land:.2f} m)")
    ref = vacuum_aim_2d(h0, ang, dist)
    print(f"真空最小速率      : {ref[0]:.2f} m/s   "
          f"(本次 {v:.2f} m/s 比它贵 {(v - ref[0]) / ref[0] * 100:+.1f}%)")
    print("完整碰撞/进球循环在 simulation.simulate_2d()；运行 `python simulation.py` 看结局。")
