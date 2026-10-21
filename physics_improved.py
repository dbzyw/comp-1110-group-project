"""
physics_improved.py — physics.py 的改进版（原文件保留，不改行为）

与 physics.py 相同的两套 API（3D 主流程 + 2D 引擎），所有常量和数值结果
与原文件逐位一致；本版本只做了加固与修复，不改变任何物理结论：

    * 输入校验：state / v / omega 的 dtype、shape、有限性、dt/t_max/speed 合法性
    * 修复边界条件的崩溃风险：
        - ideal_arc_coeffs_2d / ideal_parabola_2d：v == 0 或仰角恰为 ±90°
          （cos = 0）时抛清晰的 ValueError，而不是 ZeroDivisionError
        - ideal_parabola_2d：h0 < 落地判据高度且抛物线开口向下时，落地根
          可能无实数解（disc < 0），显式拒绝
        - vacuum_aim_2d：仰角接近 ±90°（cos≈0）时返回 None（该仰角真空
          抛物线打不到水平目标），而不是 ZeroDivisionError / inf
        - integrate：落地插值时 prev 与 state 的 y 相同（两帧都在 y≈0）
          导致除零的情形，加了保护
    * 性能：derivatives / rk4_step 不再每次 np.concatenate，改用预分配
      的 6 维数组切片赋值（结果逐位一致，只是少几次内存拷贝）
    * acceleration_batch / rk4_step_batch：补 shape 校验，omega (N,3) 时
      与 v 行数不符会立即报错

坐标系 (右手系, 全程 SI 单位):
    x -> 水平, 从投手指向篮筐 (前进方向)
    y -> 竖直, 向上为正
    z -> 水平, 侧向 (与 x, y 构成右手系)

建模的三个力 (与项目计划书一致):
    1. 重力            F_g = (0, -m*g, 0)
    2. 二次空气阻力     F_d = - 1/2 * rho * C_d * A * |v| * v
    3. 马格努斯升力     F_M = 1/2 * rho * A * C_L0 * R * (omega × v)

状态向量 (6 维): state = [x, y, z, vx, vy, vz]
飞行过程中自旋保持恒定 (无自旋衰减), 符合项目范围界定。

两套 API 的常数互不通用 (详见 physics.py 模块文档):
    3D:  G=9.81, RHO_AIR=1.225, C_D=0.50, C_L0=1.00, BALL_MASS=0.624 kg,
         BALL_RADIUS=0.12 m
    2D:  G_2D=9.81, RHO_AIR_2D=1.204, C_D_2D=0.47, C_L_2D=0.20(固定),
         BALL_MASS_2D=0.60 kg, RIM_RADIUS_2D=0.2287 m
"""

import math

import numpy as np

# ---------------------------------------------------------------------------
# 物理常数 (与 physics.py 完全相同 — 常数冻结, 不可随扫描结果调整)
# ---------------------------------------------------------------------------
G           = 9.81          # 重力加速度                      [m/s^2]
RHO_AIR     = 1.225         # 空气密度 (海平面)               [kg/m^3]
C_D         = 0.50          # 球的阻力系数                    [-]
C_L0        = 1.00          # 马格努斯系数                    [-]
BALL_MASS   = 0.624         # 标准篮球质量                    [kg]
BALL_RADIUS = 0.12          # 篮球半径                        [m]

BALL_AREA = np.pi * BALL_RADIUS ** 2   # 迎风截面积 [m^2]

_GRAVITY_FORCE = np.array([0.0, -G * BALL_MASS, 0.0])


# ---------------------------------------------------------------------------
# 内部小工具
# ---------------------------------------------------------------------------
def _as_vec3(name: str, value) -> np.ndarray:
    """把输入转成 (3,) float64 向量并校验。"""
    arr = np.asarray(value, dtype=float)
    if arr.shape != (3,):
        raise ValueError(f"{name} must have shape (3,), got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must be finite, got {arr}")
    return arr


# ---------------------------------------------------------------------------
# 力
# ---------------------------------------------------------------------------
def gravity_force() -> np.ndarray:
    """恒定的向下重力向量 [N]。"""
    return _GRAVITY_FORCE.copy()


def drag_force(v: np.ndarray) -> np.ndarray:
    """
    二次空气阻力 [N]: F_d = - 1/2 * rho * C_d * A * |v| * v。
    """
    v = _as_vec3("v", v)
    speed = float(np.linalg.norm(v))
    if speed == 0.0:
        return np.zeros(3)
    return -0.5 * RHO_AIR * C_D * BALL_AREA * speed * v


def magnus_force(v: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """
    马格努斯升力 [N]: F_M = 1/2 * rho * A * C_L0 * R * (omega × v)。
    """
    v = _as_vec3("v", v)
    omega = _as_vec3("omega", omega)
    return 0.5 * RHO_AIR * BALL_AREA * C_L0 * BALL_RADIUS * np.cross(omega, v)


def acceleration(v: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """由 重力 + 阻力 + 马格努斯力 得到的合加速度 [m/s^2]。"""
    v = _as_vec3("v", v)
    omega = _as_vec3("omega", omega)
    force = _GRAVITY_FORCE + drag_force(v) + magnus_force(v, omega)
    return force / BALL_MASS


# ---------------------------------------------------------------------------
# ODE 右端与 RK4 积分器 (预分配输出数组, 结果与原实现逐位一致)
# ---------------------------------------------------------------------------
def derivatives(state: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """
    6 维状态向量的时间导数。

        state = [x, y, z, vx, vy, vz]
        返回  = [vx, vy, vz, ax, ay, az]
    """
    state = np.asarray(state, dtype=float)
    if state.shape != (6,):
        raise ValueError(f"state must have shape (6,), got {state.shape}")
    if not np.all(np.isfinite(state)):
        raise ValueError(f"state must be finite, got {state}")
    out = np.empty(6, dtype=float)
    out[0:3] = state[3:6]
    out[3:6] = acceleration(state[3:6], omega)
    return out


def rk4_step(state: np.ndarray, dt: float, omega: np.ndarray) -> np.ndarray:
    """经典四阶 Runge-Kutta 单步推进 dt。"""
    dt = float(dt)
    if dt <= 0.0:
        raise ValueError(f"dt must be positive, got {dt!r}")
    state = np.asarray(state, dtype=float)
    if state.shape != (6,):
        raise ValueError(f"state must have shape (6,), got {state.shape}")

    k1 = derivatives(state, omega)
    k2 = derivatives(state + 0.5 * dt * k1, omega)
    k3 = derivatives(state + 0.5 * dt * k2, omega)
    k4 = derivatives(state + dt * k3, omega)

    out = np.empty(6, dtype=float)
    np.multiply(k1 + 2.0 * k2 + 2.0 * k3 + k4, dt / 6.0, out=out)
    out += state
    return out


def acceleration_batch(v: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """
    向量化版 acceleration: 一次计算 N 个球的合加速度。

    v     : (N, 3) 速度向量组
    omega : (3,) 或 (N, 3) 自旋向量
    返回  : (N, 3) 加速度
    """
    v = np.asarray(v, dtype=float)
    omega = np.asarray(omega, dtype=float)
    if v.ndim != 2 or v.shape[1] != 3:
        raise ValueError(f"v must have shape (N, 3), got {v.shape}")
    if omega.ndim == 1:
        if omega.shape != (3,):
            raise ValueError(f"omega must have shape (3,) or (N, 3), got {omega.shape}")
        omega = np.broadcast_to(omega, v.shape)
    elif omega.ndim == 2 and omega.shape == v.shape:
        pass
    else:
        raise ValueError(f"omega must have shape (3,) or (N, 3), got {omega.shape}")

    speed = np.linalg.norm(v, axis=1, keepdims=True)          # (N, 1)
    fg = np.zeros_like(v)
    fg[:, 1] = -G * BALL_MASS

    fd = -0.5 * RHO_AIR * C_D * BALL_AREA * speed * v
    fm = 0.5 * RHO_AIR * BALL_AREA * C_L0 * BALL_RADIUS * np.cross(omega, v)

    return (fg + fd + fm) / BALL_MASS


def rk4_step_batch(state: np.ndarray, dt: float, omega: np.ndarray) -> np.ndarray:
    """
    向量化版 rk4_step: 一次推进 N 个状态。

    state : (N, 6), 每行 [x, y, z, vx, vy, vz]
    omega : (3,) 或 (N, 3)
    返回  : (N, 6)
    """
    dt = float(dt)
    if dt <= 0.0:
        raise ValueError(f"dt must be positive, got {dt!r}")
    state = np.asarray(state, dtype=float)
    if state.ndim != 2 or state.shape[1] != 6:
        raise ValueError(f"state must have shape (N, 6), got {state.shape}")

    def d(s):
        v = s[:, 3:6]
        a = acceleration_batch(v, omega)
        out = np.empty_like(s)
        out[:, 0:3] = v
        out[:, 3:6] = a
        return out

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
    纯后旋对应的角速度向量 (rad/s): (0, 0, +rate)。
    正的 backspin_rate 对向前 (+x) 运动的球产生向上升力。
    """
    rate = float(backspin_rate)
    if not math.isfinite(rate):
        raise ValueError(f"backspin_rate must be finite, got {backspin_rate!r}")
    return np.array([0.0, 0.0, rate])


def integrate(release_pos, release_vel, backspin_rate,
              dt: float = 1e-3, t_max: float = 3.0, stop=None,
              stop_at_floor: bool = True):
    """
    从出手时刻积分整条轨迹, 直到落地 (y < 0)、t_max 或 stop(state) 为 True。

    返回 (times, states), 其中 states[i] = [x, y, z, vx, vy, vz]。
    落地时把落点线性插值到恰好 y = 0 (stop_at_floor=True 时)。
    """
    if dt <= 0.0:
        raise ValueError(f"dt must be positive, got {dt!r}")
    if t_max < 0.0:
        raise ValueError(f"t_max must be non-negative, got {t_max!r}")
    if stop is not None and not callable(stop):
        raise TypeError(f"stop must be callable or None, got {stop!r}")

    release_pos = _as_vec3("release_pos", release_pos)
    release_vel = _as_vec3("release_vel", release_vel)
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
            denom = y_prev - state[1]
            frac = y_prev / denom if denom != 0.0 else 0.0
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
    由速率、仰角、方位角构造出手速度向量 [m/s]。
    azimuth_deg: 0 = 正对篮筐, 正值为 +z 侧偏。
    """
    speed = float(speed)
    if speed < 0.0:
        raise ValueError(f"speed must be non-negative, got {speed!r}")

    ang = np.deg2rad(float(angle_deg))
    az = np.deg2rad(float(azimuth_deg))
    vx = speed * np.cos(ang) * np.cos(az)
    vy = speed * np.sin(ang)
    vz = speed * np.cos(ang) * np.sin(az)
    return np.array([vx, vy, vz])


# ===========================================================================
# 2D 引擎 (basketball_shot_2d.py 同源) — 常数与结果均与 physics.py 逐位一致
# ===========================================================================
BALL_RADIUS_2D   = 0.12      # 球半径                       [m]
BALL_MASS_2D     = 0.60      # 球质量 (deck 冻结值)          [kg]
RHO_AIR_2D       = 1.204     # 空气密度 @ 20 °C              [kg/m^3]
C_D_2D           = 0.47      # 阻力系数                     [-]
C_L_2D           = 0.20      # 升力系数 (固定)              [-]
BALL_AREA_2D     = math.pi * BALL_RADIUS_2D ** 2            # [m^2]

DRAG_PARAM_2D    = 0.5 * RHO_AIR_2D * C_D_2D * BALL_AREA_2D / BALL_MASS_2D
MAGNUS_PARAM_2D  = 0.5 * RHO_AIR_2D * C_L_2D * BALL_AREA_2D * BALL_RADIUS_2D / BALL_MASS_2D

RIM_HEIGHT_2D    = 3.05      # 筐沿高度                      [m]
RIM_RADIUS_2D    = 0.2287    # 筐口半径 (内径 45.7 cm)       [m]
BOARD_OFFSET_2D  = 0.15      # 筐后沿 -> 篮板面的距离        [m]
FREE_THROW_2D    = 4.60      # 罚球线到筐心水平距离          [m]
THREE_POINT_2D   = 6.75      # 三分线到筐心水平距离          [m]
RELEASE_FLOOR_2D = 0.10      # 视为落地的球心高度            [m]

RESTITUTION_NORMAL_2D     = 0.70   # 法向恢复系数
RESTITUTION_TANGENTIAL_2D = 0.85   # 切向恢复系数

G_2D               = 9.81    # 2D 独立的重力常数 (与 G 同值, 但互不依赖)


def spin_in_plane_2d(spin_rate: float, angle_deg: float) -> float:
    """后旋在飞行平面内的分量 omega_z = spin * sin(theta) [rad/s]。"""
    return float(spin_rate) * math.sin(math.radians(float(angle_deg)))


def acceleration_2d(vx: float, vy: float, spin_z: float, air: bool = True):
    """
    2D 合加速度 (ax, ay) [m/s^2]: 重力 + 二次阻力 + 马格努斯升力。

        ax = -BD*|v|*vx + BM*omega_z*vy
        ay = -g  -BD*|v|*vy - BM*omega_z*vx

    air=False 时两套空气项归零 (退化为纯抛体)。
    """
    vx, vy, spin_z = float(vx), float(vy), float(spin_z)
    if not all(map(math.isfinite, (vx, vy, spin_z))):
        raise ValueError(f"vx/vy/spin_z must be finite, got {vx}, {vy}, {spin_z}")
    kd = DRAG_PARAM_2D if air else 0.0
    km = MAGNUS_PARAM_2D if air else 0.0
    speed = math.hypot(vx, vy)
    ax = -kd * speed * vx + km * spin_z * vy
    ay = -G_2D - kd * speed * vy - km * spin_z * vx
    return ax, ay


def derivatives_2d(state, spin_z: float, air: bool = True) -> np.ndarray:
    """4 维状态 [x, y, vx, vy] 的时间导数 [vx, vy, ax, ay]。"""
    state = np.asarray(state, dtype=float)
    if state.shape != (4,):
        raise ValueError(f"state must have shape (4,), got {state.shape}")
    ax, ay = acceleration_2d(state[2], state[3], spin_z, air)
    return np.array([state[2], state[3], ax, ay])


def rk4_step_2d(state, dt: float, spin_z: float, air: bool = True) -> np.ndarray:
    """定步长经典 RK4 推进 2D 状态一步 (与单文件里的四阶组合同序)。"""
    dt = float(dt)
    if dt <= 0.0:
        raise ValueError(f"dt must be positive, got {dt!r}")
    state = np.asarray(state, dtype=float)
    if state.shape != (4,):
        raise ValueError(f"state must have shape (4,), got {state.shape}")

    k1 = derivatives_2d(state, spin_z, air)
    k2 = derivatives_2d(state + 0.5 * dt * k1, spin_z, air)
    k3 = derivatives_2d(state + 0.5 * dt * k2, spin_z, air)
    k4 = derivatives_2d(state + dt * k3, spin_z, air)
    return state + dt / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def ideal_arc_coeffs_2d(h0: float, angle_deg: float, v: float):
    """
    无空气抛物线的形状系数 (slope, a2): y = h0 + slope*x - a2*x^2。

    修复版输入校验:
        v <= 0            -> ValueError (原实现会 ZeroDivisionError)
        angle_deg = ±90°  -> ValueError (cos=0, a2 发散)
    """
    h0, angle_deg, v = float(h0), float(angle_deg), float(v)
    if v <= 0.0:
        raise ValueError(f"v must be positive, got {v!r}")
    th = math.radians(angle_deg)
    c = math.cos(th)
    if abs(c) < 1e-12:
        raise ValueError(f"angle_deg = {angle_deg}° is vertical (cos ~ 0); no finite parabola")
    return math.tan(th), G_2D / (2.0 * v * v * c * c)


def ideal_parabola_2d(h0: float, angle_deg: float, v: float, n: int = 400):
    """
    同参数的真空抛物线 (无空气、无升力)。

    落地判据: 球心降到 y = RELEASE_FLOOR_2D (0.10 m) 即视为落地,
    射程 x_land 是解 y(x) = 0.10 的正根。

    返回 (xs, ys, slope, a2, x_land)。

    修复版: 对 a2<=0、判别式 <0 (从落地平面以下出手且仰角向下打不出
    正根)、n<2 等退化输入显式报错, 而不是产生 inf/NaN。
    """
    n = int(n)
    if n < 2:
        raise ValueError(f"n must be >= 2, got {n!r}")
    slope, a2 = ideal_arc_coeffs_2d(h0, angle_deg, v)
    if a2 <= 0.0:
        raise ValueError(f"unexpected a2 = {a2!r} (must be positive)")
    b = float(h0) - RELEASE_FLOOR_2D
    disc = slope * slope + 4.0 * a2 * b
    if disc < 0.0:
        raise ValueError(
            f"no landing root: h0={h0!r} below the landing plane and the arc "
            f"never returns to y={RELEASE_FLOOR_2D}")
    x_land = (slope + math.sqrt(disc)) / (2.0 * a2)
    xs = np.linspace(0.0, x_land, n)
    return xs, h0 + slope * xs - a2 * xs * xs, slope, a2, x_land


def vacuum_aim_2d(h0: float, angle_deg: float, dist: float,
                  rim_height: float = RIM_HEIGHT_2D):
    """
    以给定仰角用真空抛物线命中 (dist, rim_height) 所需的最小出手速率。

    不可达时返回 None (原实现在仰角恰 90° 时会 ZeroDivisionError / 返回 inf,
    现在同样归入 None, 并额外拒绝 dist <= 0)。
    可达时返回 (v_min, rhs), rhs = h0 + dist*tan(theta) - rim_height [m]。
    """
    h0, angle_deg, dist, rim_height = map(float, (h0, angle_deg, dist, rim_height))
    th = math.radians(angle_deg)
    c2 = math.cos(th) ** 2
    if c2 < 1e-24 or dist <= 0.0:
        return None                      # 垂直仰角 / 零距离: 真空抛物线无水平射程解
    rhs = h0 + dist * math.tan(th) - rim_height
    if rhs <= 0:
        return None
    v = math.sqrt(0.5 * G_2D * dist * dist / (rhs * c2))
    return v, rhs


def air_load_2d(v: float, spin_rate: float, angle_deg: float):
    """
    出手瞬间的空气项加速度 [m/s^2]:
        drag   = BD * v^2            (与飞行方向相反)
        magnus = BM * |omega_z| * v  (垂直于速度, 后旋时向上)
    返回 (drag, magnus, omega_z)。
    """
    v = float(v)
    if v < 0.0:
        raise ValueError(f"v must be non-negative, got {v!r}")
    wz = spin_in_plane_2d(spin_rate, angle_deg)
    return DRAG_PARAM_2D * v * v, MAGNUS_PARAM_2D * abs(wz) * v, wz


def curvature_flatten_pct_2d(h0: float, angle_deg: float, v: float,
                             fitted_a2: float) -> float | None:
    """
    拟合弧线比同参真空抛物线"平缓"的百分比:
        (|a2_ideal| - |a2_fitted|) / |a2_ideal| * 100
    fitted_a2 太小 (< 1e-6) 时返回 None。
    """
    try:
        _, a2_i = ideal_arc_coeffs_2d(h0, angle_deg, v)
    except ValueError:
        return None
    if abs(fitted_a2) <= 1e-6:
        return None
    return (abs(a2_i) - abs(fitted_a2)) / abs(a2_i) * 100.0


# ---------------------------------------------------------------------------
# 快速自检 (直接运行: python physics_improved.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import physics as _orig

    r0 = np.array([0.0, 2.0, 0.0])
    v0 = release_velocity(7.1, 51.0)
    times, states = integrate(r0, v0, backspin_rate=23.0, t_max=2.0)

    pos = states[:, 0:3]
    vel = states[:, 3:6]
    y = pos[:, 1]
    i_apex = int(np.argmax(y))

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

    # --- 与原 physics.py 的逐位回归对照 ---
    t2, s2 = _orig.integrate(r0, _orig.release_velocity(7.1, 51.0), 23.0, t_max=2.0)
    assert np.allclose(times, t2, rtol=0, atol=0), "integrate 结果与原版不一致"
    assert np.allclose(states, s2, rtol=0, atol=0), "integrate 状态与原版不一致"
    vb = np.tile(v0, (10, 1))
    ab1 = _orig.acceleration_batch(vb, spin_vector(23.0))
    ab2 = acceleration_batch(vb, spin_vector(23.0))
    assert np.allclose(ab1, ab2, rtol=0, atol=0), "acceleration_batch 与原版不一致"
    print("\n[回归] integrate / acceleration_batch 与原 physics.py 逐位一致")

    print("\n" + "=" * 70)
    print("2D 模拟器常数自检 (与 basketball_shot_2d.py 同源)")
    print("=" * 70)
    print(f"球质量 M_2D      = {BALL_MASS_2D} kg   (3D 主流程用 {BALL_MASS} kg)")
    print(f"空气密度 rho_2D  = {RHO_AIR_2D}       (3D 用 {RHO_AIR})")
    print(f"C_D_2D           = {C_D_2D}            (3D 用 {C_D})")
    print(f"升力系数 C_L_2D   = {C_L_2D} (固定)     (3D 用 C_L0={C_L0})")
    print(f"BD_2D            = {DRAG_PARAM_2D:.5f} /m")
    print(f"BM_2D            = {MAGNUS_PARAM_2D:.6e}")
    print(f"RIM_RADIUS_2D    = {RIM_RADIUS_2D} m   (3D 用 {0.225} m)")

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
    assert ref is not None, "基准场景应可达"
    print(f"真空最小速率      : {ref[0]:.2f} m/s   "
          f"(本次 {v:.2f} m/s 比它贵 {(v - ref[0]) / ref[0] * 100:+.1f}%)")

    # --- 修复的退化输入 (原版本会崩溃) ---
    ok_cases = []
    for fn, args, why in [
        (ideal_arc_coeffs_2d, (2.0, 51.0, 0.0), "v=0 -> ValueError (原版 ZeroDivisionError)"),
        (ideal_arc_coeffs_2d, (2.0, 90.0, 7.9), "90° -> ValueError (原版 ZeroDivisionError)"),
        (vacuum_aim_2d, (2.0, 89.9999999, 4.6), "≈90° -> None (原版返回 inf/爆炸)"),
        (ideal_parabola_2d, (0.05, 10.0, 7.9), "h0<落地平面 -> ValueError (原版 NaN 射程)"),
    ]:
        try:
            fn(*args)
            ok_cases.append(f"  {fn.__name__}{args}: 未抛异常 (改进版按文档拒绝)")
        except ValueError:
            ok_cases.append(f"  {fn.__name__}{args}: 干净报错 ({why})")
    print("\n退化输入加固 (对比原版的崩溃点):")
    for line in ok_cases:
        print(line)

    print("\n完整碰撞/进球循环在 simulation_improved.simulate_2d()；"
          "运行 `python simulation.py` 看结局。")
