"""
collision.py — 篮球(球体)与篮板(竖直平面)、篮筐(圆环)的碰撞检测与恢复系数反弹。

几何约定 (与 physics.py 同一右手系, SI 单位):
    x -> 从投手指向篮筐 (前进方向)
    y -> 竖直向上
    z -> 侧向

NBA 场地尺寸 (用户确定):
    篮筐高度            3.05 m
    篮筐直径            0.45 m   (半径 0.225 m)
    篮筐中心距篮板面    0.375 m
    篮板 (竖直平面) 位于 x = 0, 投手在 -x 一侧 (球沿 +x 飞向篮板)。

模型:
    篮板:  球体 vs 竖直平面 (平面-球接触)。仅当接触点落在篮板矩形
           (宽 1.8 m、高 1.05 m、下沿 2.9 m) 内才判定碰撞。
    篮筐:  球体 vs 圆环。把篮筐当作水平面内半径 RIM_RADIUS 的细圆环,
           取球心到圆环最近点的距离 d; d <= 球半径 即发生碰撞。
           球心正对筐心 (水平方向 r≈0) 时视为空心入网, 不碰撞。

反弹:
    只改变沿碰撞法向 n 的速度分量, 乘以恢复系数 e = 0.7;
    切向分量不变 (项目范围: 单一恢复系数, 无摩擦/侧旋)。
"""

import numpy as np
from dataclasses import dataclass

try:
    from physics import BALL_RADIUS
except ImportError:
    BALL_RADIUS = 0.12          # 篮球半径 [m]

# ---------------------------------------------------------------------------
# NBA 场地几何常数 (后续可迁移到 constants.py)
# ---------------------------------------------------------------------------
RIM_HEIGHT       = 3.05         # 篮筐高度 [m]
RIM_DIAMETER     = 0.45         # 篮筐直径 [m]
RIM_RADIUS       = RIM_DIAMETER / 2.0      # 0.225 m
RIM_TO_BOARD     = 0.375        # 筐心到篮板面距离 [m]

BACKBOARD_X      = 0.0          # 篮板所在竖直平面 x = 0
BACKBOARD_WIDTH  = 1.8          # 篮板宽度 (z 方向) [m]
BACKBOARD_HEIGHT = 1.05         # 篮板高度 (y 方向) [m]
BACKBOARD_BOTTOM = 2.9          # 篮板下沿高度 [m]
BACKBOARD_TOP    = BACKBOARD_BOTTOM + BACKBOARD_HEIGHT   # 3.95 m
BACKBOARD_HALF_WIDTH = BACKBOARD_WIDTH / 2.0             # 0.9 m

# 筐心坐标: 在篮板前方 (投手一侧) 0.375 m 处
RIM_CENTER = np.array([-RIM_TO_BOARD, RIM_HEIGHT, 0.0])  # (-0.375, 3.05, 0)

# 恢复系数
RESTITUTION = 0.7


# ---------------------------------------------------------------------------
# 碰撞结果
# ---------------------------------------------------------------------------
@dataclass
class Collision:
    kind: str                  # "backboard" | "rim"
    normal: np.ndarray         # 单位法向, 从接触表面指向球心
    penetration: float         # 嵌入深度 (>= 0)
    contact: np.ndarray        # 接触点 (表面上的点)


# ---------------------------------------------------------------------------
# 碰撞检测
# ---------------------------------------------------------------------------
def detect_backboard(pos) -> "Collision | None":
    """
    检测球体与篮板 (竖直平面 x = BACKBOARD_X) 的碰撞。

    pos : array_like, shape (3,)  球心位置 [x, y, z]。

    返回 Collision, 未碰撞返回 None。
    """
    x, y, z = float(pos[0]), float(pos[1]), float(pos[2])

    # 球面到篮板面的嵌入深度 = 球半径 - |球心到板面距离| (两侧通用)
    penetration = BALL_RADIUS - abs(x - BACKBOARD_X)
    if penetration < 0.0:
        return None

    # 接触点必须落在篮板矩形范围内 (否则球从篮板四周/上沿飞过)
    if not (BACKBOARD_BOTTOM <= y <= BACKBOARD_TOP):
        return None
    if abs(z) > BACKBOARD_HALF_WIDTH:
        return None

    # 法向从板面指向球心: 球在 -x 侧 -> (-1,0,0); 在 +x 侧 -> (+1,0,0)
    normal = np.array([-1.0, 0.0, 0.0] if x < BACKBOARD_X else [1.0, 0.0, 0.0])
    contact = np.array([BACKBOARD_X, y, z])
    return Collision("backboard", normal, float(penetration), contact)


def detect_rim(pos) -> "Collision | None":
    """
    检测球体与篮筐 (水平圆环) 的碰撞。

    篮筐是 y = RIM_HEIGHT 平面内、圆心 RIM_CENTER、半径 RIM_RADIUS 的细圆环。
    计算球心到圆环最近点的距离 d, 若 d <= 球半径则碰撞。

    pos : array_like, shape (3,)  球心位置 [x, y, z]。

    返回 Collision, 未碰撞返回 None。
    """
    c = np.asarray(pos, dtype=float)
    cx, cy, cz = c[0], c[1], c[2]

    # 球心相对筐心的水平偏移
    hx = cx - RIM_CENTER[0]
    hz = cz - RIM_CENTER[2]
    r = float(np.hypot(hx, hz))

    if r < 1e-12:
        # 球心水平正对筐心: 走空心 (swish) 路径, 不碰撞
        return None

    # 圆环上离球心最近的点
    px = RIM_CENTER[0] + RIM_RADIUS * hx / r
    pz = RIM_CENTER[2] + RIM_RADIUS * hz / r
    py = RIM_CENTER[1]
    p = np.array([px, py, pz])

    dvec = c - p
    d = float(np.linalg.norm(dvec))

    penetration = BALL_RADIUS - d
    if penetration < 0.0:
        return None

    normal = dvec / d                  # 从接触点指向球心
    return Collision("rim", normal, penetration, p)


def detect_any(pos) -> "Collision | None":
    """同时检测篮板与篮筐, 返回其中任意一个碰撞 (篮板优先)。"""
    c = detect_backboard(pos)
    if c is not None:
        return c
    return detect_rim(pos)


def detect_backboard_batch(pos):
    """
    向量化篮板碰撞检测。

    pos : np.ndarray, shape (N, 3)  球心位置组
    返回 (hit (N,), normal (N,3), penetration (N,))。
    """
    pos = np.asarray(pos, dtype=float)
    N = pos.shape[0]
    x = pos[:, 0]
    y = pos[:, 1]
    z = pos[:, 2]

    pen = BALL_RADIUS - np.abs(x - BACKBOARD_X)
    hit = ((pen >= 0.0) & (y >= BACKBOARD_BOTTOM) & (y <= BACKBOARD_TOP)
           & (np.abs(z) <= BACKBOARD_HALF_WIDTH))

    normal = np.zeros((N, 3))
    normal[:, 0] = np.where(x < BACKBOARD_X, -1.0, 1.0)
    return hit, normal, pen


def detect_rim_batch(pos):
    """
    向量化篮筐(圆环)碰撞检测。

    pos : np.ndarray, shape (N, 3)  球心位置组
    返回 (hit (N,), normal (N,3), penetration (N,))。
    """
    pos = np.asarray(pos, dtype=float)
    N = pos.shape[0]
    cx = pos[:, 0]
    cy = pos[:, 1]
    cz = pos[:, 2]

    hx = cx - RIM_CENTER[0]
    hz = cz - RIM_CENTER[2]
    r = np.hypot(hx, hz)
    valid = r > 1e-12

    safe_r = np.where(valid, r, 1.0)
    px = RIM_CENTER[0] + RIM_RADIUS * hx / safe_r
    pz = RIM_CENTER[2] + RIM_RADIUS * hz / safe_r
    py = np.full(N, RIM_CENTER[1])

    dx = cx - px
    dy = cy - py
    dz = cz - pz
    d = np.sqrt(dx * dx + dy * dy + dz * dz)
    pen = BALL_RADIUS - d
    hit = valid & (pen >= 0.0)

    safe_d = np.where(d > 0.0, d, 1.0)
    normal = np.zeros((N, 3))
    normal[:, 0] = np.where(hit, dx / safe_d, 0.0)
    normal[:, 1] = np.where(hit, dy / safe_d, 0.0)
    normal[:, 2] = np.where(hit, dz / safe_d, 0.0)
    return hit, normal, pen


# ---------------------------------------------------------------------------
# 反弹
# ---------------------------------------------------------------------------
def reflect(vel, normal, e: float = RESTITUTION) -> np.ndarray:
    """
    用恢复系数 e 沿法向反弹速度 (切向不变)。

        v_n = v · n
        v'  = v - (1 + e) * v_n * n      (仅当 v_n < 0, 即正接近表面时)

    vel    : array_like, shape (3,)  碰撞前速度 [m/s]
    normal : array_like, shape (3,)  单位碰撞法向 (从表面指向球心)
    e      : float  恢复系数, 默认 0.7

    返回反弹后的速度向量。
    """
    v = np.asarray(vel, dtype=float)
    n = np.asarray(normal, dtype=float)
    vn = float(np.dot(v, n))
    if vn < 0.0:
        v = v - (1.0 + e) * vn * n
    return v


def resolve(pos, vel, collision: Collision, correct_position: bool = True):
    """
    根据碰撞信息更新位置与速度。

    pos        : 碰撞前球心位置 [x, y, z]
    vel        : 碰撞前速度 [m/s]
    collision  : detect_* 返回的 Collision
    correct_position : 是否沿法向把球推出嵌入 (默认 True)

    返回 (新位置, 新速度)。
    """
    new_vel = reflect(vel, collision.normal, RESTITUTION)
    new_pos = np.asarray(pos, dtype=float)
    if correct_position and collision.penetration > 0.0:
        new_pos = new_pos + collision.normal * collision.penetration
    return new_pos, new_vel


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------
def _show(title, pos, vel, c):
    print(f"\n【{title}】")
    print(f"  碰撞前  pos = [{pos[0]:+.4f}, {pos[1]:+.4f}, {pos[2]:+.4f}]")
    print(f"          vel = [{vel[0]:+.4f}, {vel[1]:+.4f}, {vel[2]:+.4f}]")
    if c is None:
        print("  -> 未碰撞 (球自由飞行 / 空心入网)")
        return
    new_pos, new_vel = resolve(pos, vel, c)
    print(f"  kind        = {c.kind}")
    print(f"  normal      = [{c.normal[0]:+.4f}, {c.normal[1]:+.4f}, {c.normal[2]:+.4f}]")
    print(f"  penetration = {c.penetration:.4f} m")
    print(f"  碰撞后  pos = [{new_pos[0]:+.4f}, {new_pos[1]:+.4f}, {new_pos[2]:+.4f}]")
    print(f"          vel = [{new_vel[0]:+.4f}, {new_vel[1]:+.4f}, {new_vel[2]:+.4f}]")


def run_tests():
    print("=" * 66)
    print("collision.py 自检 (恢复系数 e = %.1f, 球半径 = %.2f m)"
          % (RESTITUTION, BALL_RADIUS))
    print("=" * 66)

    # 1) 篮板正面撞击: 球沿 +x 撞向篮板
    pos = np.array([-0.10, 3.20, 0.0])
    vel = np.array([5.0, -2.0, 0.0])
    _show("篮板正面撞击", pos, vel, detect_backboard(pos))

    # 2) 篮筐前缘: 球下落砸在篮筐前边缘
    pos = np.array([-0.60, 3.15, 0.0])
    vel = np.array([1.0, -3.0, 0.0])
    _show("篮筐前缘下落撞击", pos, vel, detect_rim(pos))

    # 3) 篮筐侧缘斜向撞击 (带 z 偏移, 法向非轴对称)
    pos = np.array([-0.375, 3.05, 0.29])
    vel = np.array([0.5, -2.5, -1.0])
    _show("篮筐侧缘斜向撞击", pos, vel, detect_rim(pos))

    # 4) 空心入网: 球心正对筐心下落, 不应碰撞
    pos = np.array([-0.375, 3.10, 0.0])
    vel = np.array([0.0, -3.0, 0.0])
    _show("空心入网 (swish)", pos, vel, detect_rim(pos))

    # 5) 从篮板上沿飞过: 球心高于篮板上沿, 不应碰撞
    pos = np.array([-0.10, 4.00, 0.0])
    vel = np.array([3.0, -1.0, 0.0])
    _show("越过篮板上沿 (无碰撞)", pos, vel, detect_backboard(pos))

    print("\n" + "=" * 66)


if __name__ == "__main__":
    run_tests()
