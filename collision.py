"""Basketball collision detection and response for a rectangular backboard and rim.

Coordinates use SI units: x points from the shooter towards the hoop, y is up,
and z is lateral.  The backboard is a finite, zero-thickness rectangle at x=0;
the rim is a thin horizontal circle.  Contact response uses a frictionless,
constant-coefficient-of-restitution model.

同一文件里有两套碰撞 API（两套恢复系数不同，不可混用）：

  3D 主流程（上半部分，与 physics.py 的 3D 常数配套）：
      矩形篮板 / 圆环篮筐 与球的嵌入检测（含边缘与角落），
      单一法向恢复系数 e = 0.70，可选切向保留比例 TANGENTIAL_RETENTION（默认 1.0，
      即无摩擦），位置校正与多接触有限轮迭代。

  2D 模拟器（下半部分，*_2D 后缀，与根目录 basketball_shot_2d.py 同源）：
      把篮板看成一条竖直面（只在球心“本步实际穿越平面”且接触高度落在板面窗口内
      才触发反弹），把筐口看成前后两个刚性圆点，法向恢复 0.70 + 切向恢复 0.85，
      进球用“穿面 + 筐口内沿两侧各留 12 mm 余量”判据。

两套几何常数不同（3D 筐半径 0.225 m，2D 用 0.2287 m），引用结果时必须注明是哪套。
"""

import math
from dataclasses import dataclass

import numpy as np

try:
    from physics import BALL_RADIUS
except ImportError:  # Keep this module usable by itself for demonstrations/tests.
    BALL_RADIUS = 0.12

try:
    from physics import (BALL_RADIUS_2D, RIM_HEIGHT_2D, RIM_RADIUS_2D,
                         BOARD_OFFSET_2D, FREE_THROW_2D,
                         RESTITUTION_NORMAL_2D, RESTITUTION_TANGENTIAL_2D)
except ImportError:  # 允许单独作为脚本运行 / 无物理模块时也能演示 2D 几何。
    BALL_RADIUS_2D = 0.12
    RIM_HEIGHT_2D = 3.05
    RIM_RADIUS_2D = 0.2287
    BOARD_OFFSET_2D = 0.15
    FREE_THROW_2D = 4.60
    RESTITUTION_NORMAL_2D = 0.70
    RESTITUTION_TANGENTIAL_2D = 0.85


# Geometry (metres)
RIM_HEIGHT = 3.05
RIM_DIAMETER = 0.45
RIM_RADIUS = RIM_DIAMETER / 2.0
RIM_TO_BOARD = 0.375
BACKBOARD_X = 0.0
BACKBOARD_WIDTH = 1.8
BACKBOARD_HEIGHT = 1.05
BACKBOARD_BOTTOM = 2.9
BACKBOARD_TOP = BACKBOARD_BOTTOM + BACKBOARD_HEIGHT
BACKBOARD_HALF_WIDTH = BACKBOARD_WIDTH / 2.0
RIM_CENTER = np.array([-RIM_TO_BOARD, RIM_HEIGHT, 0.0])
BACKBOARD_RESTITUTION = 0.7
RIM_RESTITUTION = 0.7
# Backwards-compatible default used by callers that still pass RESTITUTION.
RESTITUTION = BACKBOARD_RESTITUTION
# Fraction of tangential velocity retained in the simplified friction model.
# 1.0 means frictionless contact; 0.0 removes tangential velocity at impact.
TANGENTIAL_RETENTION = 1.0


@dataclass
class Collision:
    """A detected contact; normal points from the surface towards the ball."""

    kind: str
    normal: np.ndarray
    penetration: float
    contact: np.ndarray


def _vector3(value, name):
    """Return a finite float vector of shape (3,), otherwise raise ValueError."""
    vector = np.asarray(value, dtype=float)
    if vector.shape != (3,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite vector with shape (3,)")
    return vector


def _positive_scalar(value, name):
    """Validate a positive finite scalar parameter."""
    value = float(value)
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")
    return value


def detect_backboard(pos, ball_radius: float = BALL_RADIUS) -> Collision | None:
    """Detect a sphere touching the finite rectangular backboard.

    The nearest point on the rectangle is used, so edge and corner contacts are
    included (unlike an infinite-plane test clipped by the ball-centre bounds).
    """
    center = _vector3(pos, "pos")
    ball_radius = _positive_scalar(ball_radius, "ball_radius")
    contact = np.array([
        BACKBOARD_X,
        np.clip(center[1], BACKBOARD_BOTTOM, BACKBOARD_TOP),
        np.clip(center[2], -BACKBOARD_HALF_WIDTH, BACKBOARD_HALF_WIDTH),
    ])
    delta = center - contact
    distance = float(np.linalg.norm(delta))
    penetration = ball_radius - distance
    if penetration < 0.0:
        return None

    if distance > 1e-12:
        normal = delta / distance
    else:
        # The centre lies on the ideal zero-thickness board; choose a stable side.
        normal = np.array([-1.0, 0.0, 0.0] if center[0] < BACKBOARD_X
                          else [1.0, 0.0, 0.0])
    return Collision("backboard", normal, penetration, contact)


def detect_rim(pos, ball_radius: float = BALL_RADIUS) -> Collision | None:
    """Detect sphere contact with the thin horizontal circular rim."""
    center = _vector3(pos, "pos")
    ball_radius = _positive_scalar(ball_radius, "ball_radius")
    horizontal = center[[0, 2]] - RIM_CENTER[[0, 2]]
    radius = float(np.linalg.norm(horizontal))

    # At the symmetry axis every rim point is equally close; select one point.
    # This also avoids a zero-divide and gives the correct centre-to-ring distance.
    if radius > 1e-12:
        radial_direction = horizontal / radius
    else:
        radial_direction = np.array([1.0, 0.0])

    contact = np.array([
        RIM_CENTER[0] + RIM_RADIUS * radial_direction[0],
        RIM_HEIGHT,
        RIM_CENTER[2] + RIM_RADIUS * radial_direction[1],
    ])
    delta = center - contact
    distance = float(np.linalg.norm(delta))
    penetration = ball_radius - distance
    if penetration < 0.0:
        return None

    # For the project's dimensions distance cannot be zero, but keep the normal
    # well-defined if dimensions are changed in a future version.
    if distance > 1e-12:
        normal = delta / distance
    else:
        normal = np.array([1.0, 0.0, 0.0])
    return Collision("rim", normal, penetration, contact)


def detect_any(pos, ball_radius: float = BALL_RADIUS) -> Collision | None:
    """Return a backboard contact first, otherwise a rim contact."""
    collisions = detect_all(pos, ball_radius)
    return collisions[0] if collisions else None


def detect_all(pos, ball_radius: float = BALL_RADIUS) -> list[Collision]:
    """Return every overlapping contact, in stable backboard-then-rim order."""
    collisions = []
    backboard = detect_backboard(pos, ball_radius)
    rim = detect_rim(pos, ball_radius)
    if backboard is not None:
        collisions.append(backboard)
    if rim is not None:
        collisions.append(rim)
    return collisions


def detect_backboard_batch(pos, ball_radius: float = BALL_RADIUS):
    """Vectorised rectangular-board test; returns hit, normal, penetration."""
    ball_radius = _positive_scalar(ball_radius, "ball_radius")
    centers = np.asarray(pos, dtype=float)
    if centers.ndim != 2 or centers.shape[1] != 3 or not np.all(np.isfinite(centers)):
        raise ValueError("pos must be a finite array with shape (N, 3)")

    contacts = np.column_stack((
        np.full(len(centers), BACKBOARD_X),
        np.clip(centers[:, 1], BACKBOARD_BOTTOM, BACKBOARD_TOP),
        np.clip(centers[:, 2], -BACKBOARD_HALF_WIDTH, BACKBOARD_HALF_WIDTH),
    ))
    delta = centers - contacts
    distance = np.linalg.norm(delta, axis=1)
    penetration = ball_radius - distance
    hit = penetration >= 0.0

    normals = np.zeros_like(centers)
    nonzero = hit & (distance > 1e-12)
    normals[nonzero] = delta[nonzero] / distance[nonzero, None]
    centered = hit & ~nonzero
    normals[centered, 0] = np.where(centers[centered, 0] < BACKBOARD_X, -1.0, 1.0)
    return hit, normals, penetration


def detect_rim_batch(pos, ball_radius: float = BALL_RADIUS):
    """Vectorised rim test; returns hit, normal, penetration."""
    ball_radius = _positive_scalar(ball_radius, "ball_radius")
    centers = np.asarray(pos, dtype=float)
    if centers.ndim != 2 or centers.shape[1] != 3 or not np.all(np.isfinite(centers)):
        raise ValueError("pos must be a finite array with shape (N, 3)")

    horizontal = centers[:, [0, 2]] - RIM_CENTER[[0, 2]]
    radius = np.linalg.norm(horizontal, axis=1)
    direction = np.zeros_like(horizontal)
    off_axis = radius > 1e-12
    direction[off_axis] = horizontal[off_axis] / radius[off_axis, None]
    direction[~off_axis, 0] = 1.0

    contacts = np.column_stack((
        RIM_CENTER[0] + RIM_RADIUS * direction[:, 0],
        np.full(len(centers), RIM_HEIGHT),
        RIM_CENTER[2] + RIM_RADIUS * direction[:, 1],
    ))
    delta = centers - contacts
    distance = np.linalg.norm(delta, axis=1)
    penetration = ball_radius - distance
    hit = penetration >= 0.0

    normals = np.zeros_like(centers)
    nonzero = hit & (distance > 1e-12)
    normals[nonzero] = delta[nonzero] / distance[nonzero, None]
    normals[hit & ~nonzero, 0] = 1.0
    return hit, normals, penetration


def reflect(vel, normal, e: float = RESTITUTION,
            tangential_retention: float = TANGENTIAL_RETENTION) -> np.ndarray:
    """Reflect approaching velocity with restitution and simple tangential loss.

    With outward unit normal n and incoming normal speed v_n = v·n < 0,
    v_after = -e*v_n*n + tangential_retention*v_t, where v_t is the incoming
    tangential velocity. Separating contacts are unchanged. The retention
    parameter is a simplified friction control, not a Coulomb friction model.
    """
    velocity = _vector3(vel, "vel")
    normal = _vector3(normal, "normal")
    norm = float(np.linalg.norm(normal))
    if not np.isclose(norm, 1.0, atol=1e-8):
        raise ValueError("normal must be a unit vector")
    if not np.isfinite(e) or not 0.0 <= e <= 1.0:
        raise ValueError("e must be between 0 and 1")
    if not np.isfinite(tangential_retention) or not 0.0 <= tangential_retention <= 1.0:
        raise ValueError("tangential_retention must be between 0 and 1")

    normal_speed = float(np.dot(velocity, normal))
    if normal_speed < 0.0:
        tangent_velocity = velocity - normal_speed * normal
        velocity = (-e * normal_speed * normal
                    + tangential_retention * tangent_velocity)
    return velocity


def resolve(pos, vel, collision: Collision, correct_position: bool = True,
            restitution: float | None = None,
            tangential_retention: float = TANGENTIAL_RETENTION):
    """Apply one contact response and optionally remove geometric overlap."""
    position = _vector3(pos, "pos").copy()
    if restitution is None:
        restitution = restitution_for(collision.kind)
    velocity = reflect(vel, collision.normal, restitution, tangential_retention)
    if correct_position and collision.penetration > 0.0:
        position += collision.normal * collision.penetration
    return position, velocity


def restitution_for(kind: str) -> float:
    """Return the configured restitution for a supported contact kind."""
    if kind == "backboard":
        return BACKBOARD_RESTITUTION
    if kind == "rim":
        return RIM_RESTITUTION
    raise ValueError(f"unsupported collision kind: {kind}")


def resolve_contacts(pos, vel, collisions=None, correct_position: bool = True,
                     tangential_retention: float = TANGENTIAL_RETENTION,
                     max_position_iterations: int = 4,
                     max_velocity_iterations: int = 4,
                     ball_radius: float = BALL_RADIUS):
    """Resolve all contacts found at a position using bounded sequential passes.

    Each incoming contact applies its own restitution in stable order. A few
    sequential passes reduce order bias when two contact normals compete.
    Position overlap is corrected iteratively. This is a lightweight
    multi-contact approximation, not a full impulse/contact-manifold solver.
    """
    position = _vector3(pos, "pos").copy()
    velocity = _vector3(vel, "vel").copy()
    ball_radius = _positive_scalar(ball_radius, "ball_radius")
    if collisions is None:
        collisions = detect_all(position, ball_radius)
    else:
        collisions = list(collisions)
    if max_position_iterations < 1:
        raise ValueError("max_position_iterations must be at least 1")
    if max_velocity_iterations < 1:
        raise ValueError("max_velocity_iterations must be at least 1")

    for iteration in range(max_velocity_iterations):
        any_approaching = False
        for collision in collisions:
            normal = _vector3(collision.normal, "collision.normal")
            if np.dot(velocity, normal) < -1e-10:
                # Apply material restitution once. Later passes only remove
                # newly introduced inward velocity, preventing repeated
                # restitution from artificially adding energy at one contact.
                restitution = (restitution_for(collision.kind)
                               if iteration == 0 else 0.0)
                velocity = reflect(
                    velocity,
                    normal,
                    restitution,
                    tangential_retention if iteration == 0 else 1.0,
                )
                any_approaching = True
        if not any_approaching:
            break

    if correct_position:
        for _ in range(max_position_iterations):
            current_contacts = detect_all(position, ball_radius)
            penetrating = [c for c in current_contacts if c.penetration > 1e-10]
            if not penetrating:
                break
            # Try each single-contact projection and keep the one that most
            # reduces total squared overlap. This avoids oscillating forever
            # between opposing surfaces when the sphere physically cannot fit.
            current_error = sum(c.penetration ** 2 for c in penetrating)
            best_position = position
            best_error = current_error
            for contact in penetrating:
                candidate = position + contact.normal * contact.penetration
                candidate_contacts = detect_all(candidate, ball_radius)
                candidate_error = sum(
                    c.penetration ** 2 for c in candidate_contacts
                    if c.penetration > 1e-10
                )
                if candidate_error + 1e-14 < best_error:
                    best_position = candidate
                    best_error = candidate_error
            if best_error >= current_error - 1e-14:
                # The remaining overlap is unsatisfiable under the current
                # idealised geometry (e.g. a ball squeezed between surfaces).
                break
            position = best_position

    return position, velocity


# ---------------------------------------------------------------------------
# 2D 碰撞层 (basketball_shot_2d.py 同源)
# ---------------------------------------------------------------------------
# 2D 模型把篮板看成一条竖直面、把筐口看成前后两个刚性圆点，用“步内是否
# 实际穿过平面”作为触发条件，而不是把零厚度矩形当成可反复嵌入的目标：
#   - 擦板而过（从正面飞到板后）不会被“瞬移”回板上，而是继续落地；
#   - 法向乘 EN、切向乘 ET（两者不同），与 3D 主流程的单一 e=0.70 不同。

# 板面接触高度窗口（deck：筐沿下 0.30 m 到上 0.80 m）
BOARD_CONTACT_BOTTOM_2D = RIM_HEIGHT_2D - 0.30
BOARD_CONTACT_TOP_2D    = RIM_HEIGHT_2D + 0.80
BOARD_CONTACT_WINDOW_2D = (BOARD_CONTACT_BOTTOM_2D, BOARD_CONTACT_TOP_2D)

# 筐口内沿余量：球心向下穿过筐面时，水平位置必须落在 [xF + margin, xB - margin]
OPENING_MARGIN_2D = 0.012

# 同一次飞行中允许几次板面反弹（防死循环）
MAX_BOARD_BOUNCES_2D = 4


def hoop_geometry_2d(center_x: float, *, rim_radius: float = RIM_RADIUS_2D,
                     ball_radius: float = BALL_RADIUS_2D,
                     board_offset: float = BOARD_OFFSET_2D):
    """
    由筐心水平坐标算 2D 场景的三点：前缘 xF、后缘 xB、以及触发板面反弹的
    xbc（篮板接触参考面，位于后缘 + 板后间隙 - 球半径）。

    对应单文件的 `hoop_geoms`：xF = c - R, xB = c + R, xbc = xB + BOARD_OFF - R。
    返回 (xF, xB, xbc)。
    """
    c = float(center_x)
    xF = c - rim_radius
    xB = c + rim_radius
    return xF, xB, xB + board_offset - ball_radius


def reflect_2d(vx: float, vy: float, nx: float, ny: float,
               e_n: float = RESTITUTION_NORMAL_2D,
               e_t: float = RESTITUTION_TANGENTIAL_2D):
    """
    2D 接触反弹：把速度拆成法向 / 切向，法向乘 -e_n、切向乘 e_t。

        v_n = v · n,  v_t = v - v_n n
        v'  = -e_n * v_n * n + e_t * v_t     (仅当 v_n < 0, 即正在接近)

    已在离开或纯切向擦过时原速度不变。返回 (vx', vy')。
    """
    vx, vy = float(vx), float(vy)
    nx, ny = float(nx), float(ny)
    if not np.isclose(math.hypot(nx, ny), 1.0, atol=1e-8):
        raise ValueError("normal must be a unit 2D vector")
    if not 0.0 <= e_n <= 1.0:
        raise ValueError("e_n must be between 0 and 1")
    if not 0.0 <= e_t <= 1.0:
        raise ValueError("e_t must be between 0 and 1")
    vn = vx * nx + vy * ny
    if vn >= 0.0:
        return vx, vy
    tx, ty = vx - vn * nx, vy - vn * ny
    return e_t * tx - e_n * vn * nx, e_t * ty - e_n * vn * ny


def cross_board_plane_2d(prev, nxt, board_x: float,
                         height_window=BOARD_CONTACT_WINDOW_2D):
    """
    检查球心在 [prev, nxt] 这一步内是否实际穿过了板面 x = board_x，
    且接触点高度在板面窗口内。

    prev, nxt 为 4 维状态 [x, y, vx, vy]。用步内线性插值求穿越点的位置与速度。
    未穿越（同号）或穿越但高度不在窗口内时返回 None。
    """
    prev = np.asarray(prev, dtype=float)
    nxt = np.asarray(nxt, dtype=float)
    if prev.shape != (4,) or nxt.shape != (4,):
        raise ValueError("prev/nxt must be finite 4-vectors [x, y, vx, vy]")
    board_x = float(board_x)
    if (prev[0] - board_x) * (nxt[0] - board_x) >= 0.0:
        return None
    w = (board_x - prev[0]) / (nxt[0] - prev[0])
    yc = prev[1] + w * (nxt[1] - prev[1])
    lo, hi = height_window
    if not (lo <= yc <= hi):
        return None
    vxc = prev[2] + w * (nxt[2] - prev[2])
    vyc = prev[3] + w * (nxt[3] - prev[3])
    return dict(w=float(w), x=board_x, y=float(yc), vx=float(vxc), vy=float(vyc))


def bounce_off_board_2d(prev, nxt, board_x: float, t_contact: float, *,
                        height_window=BOARD_CONTACT_WINDOW_2D,
                        e_n: float = RESTITUTION_NORMAL_2D,
                        e_t: float = RESTITUTION_TANGENTIAL_2D):
    """
    板面反弹：若这一步确实穿越了板面且接触高度在窗口内，把状态放到穿越点
    并反弹。返回 (new_state, contact_dict) 或 None。

    contact_dict 与单文件的记录同构：
        kind/t/x/y/tin/tout/face（'front' = 从投手一侧撞正面，'back' = 从板后撞背面）
    """
    info = cross_board_plane_2d(prev, nxt, board_x, height_window)
    if info is None:
        return None
    # 板是竖直面：法向沿 x，指向球心来的一侧（vxc > 0 表示从 -x 侧撞向板）
    nx = -1.0 if info["vx"] > 0.0 else 1.0
    vxr, vyr = reflect_2d(info["vx"], info["vy"], nx, 0.0, e_n, e_t)
    state = np.array([info["x"], info["y"], vxr, vyr], dtype=float)
    contact = dict(kind="board", t=float(t_contact), x=float(info["x"]),
                   y=float(info["y"]), tin=(info["vx"], info["vy"]),
                   tout=(vxr, vyr), face="front" if info["vx"] > 0 else "back")
    return state, contact


def rim_edge_gap_2d(state, edge_x: float, *, rim_y: float = RIM_HEIGHT_2D,
                    ball_radius: float = BALL_RADIUS_2D):
    """
    球心到 2D 筐沿端点（当作刚性圆点）的距离与重叠量：
    返回 (distance, penetration, (nx, ny))；无接触时 penetration < 0。
    """
    state = np.asarray(state, dtype=float)
    dx = float(state[0]) - float(edge_x)
    dy = float(state[1]) - float(rim_y)
    dd = math.hypot(dx, dy)
    if dd <= 1e-9:
        return dd, float(ball_radius), (1.0, 0.0)
    return dd, float(ball_radius) - dd, (dx / dd, dy / dd)


def detect_rim_edges_2d(state, xF: float, xB: float, *,
                        rim_y: float = RIM_HEIGHT_2D,
                        ball_radius: float = BALL_RADIUS_2D):
    """
    对前后两个筐沿端点做接触检测，返回接触列表
    [(edge_x, distance, penetration, (nx, ny))]（按 xF, xB 顺序，只包含重叠的）。
    """
    out = []
    for xe in (float(xF), float(xB)):
        dd, pen, normal = rim_edge_gap_2d(state, xe, rim_y=rim_y,
                                          ball_radius=ball_radius)
        if pen > 0.0 and dd > 1e-9:
            out.append((xe, dd, pen, normal))
    return out


def bounce_off_rim_edge_2d(state, edge_x: float, t_contact: float, *,
                           rim_y: float = RIM_HEIGHT_2D,
                           ball_radius: float = BALL_RADIUS_2D,
                           e_n: float = RESTITUTION_NORMAL_2D,
                           e_t: float = RESTITUTION_TANGENTIAL_2D):
    """
    单个筐沿端点的反弹：法向乘 -e_n、切向乘 e_t，并把球心沿法向推到接触面外
    （去穿透）。只在法向速度朝内（v_n < 0）时触发，避免球离开筐沿时二次触发。

    返回 (new_state, contact_dict) 或 None（未接触 / 正在离开）。
    contact_dict: kind/t/x/y/tin/tout/edge（'back' = 靠近篮板一侧，'front' = 远侧）
    """
    state = np.asarray(state, dtype=float).copy()
    dd, pen, (nx, ny) = rim_edge_gap_2d(state, edge_x, rim_y=rim_y,
                                        ball_radius=ball_radius)
    if dd <= 1e-9 or pen <= 0.0:
        return None
    vn = state[2] * nx + state[3] * ny
    if vn >= 0.0:
        return None
    tin = (float(state[2]), float(state[3]))
    vxr, vyr = reflect_2d(state[2], state[3], nx, ny, e_n, e_t)
    new_state = np.array([state[0] + pen * nx, state[1] + pen * ny, vxr, vyr],
                         dtype=float)
    contact = dict(kind="rim", t=float(t_contact), x=float(edge_x),
                   y=float(rim_y), tin=tin, tout=(vxr, vyr),
                   edge="back" if (float(state[0]) - float(edge_x)) > 0 else "front")
    return new_state, contact


def detect_scoring_cross_2d(prev, nxt, xF: float, xB: float, *,
                            rim_y: float = RIM_HEIGHT_2D,
                            opening_margin: float = OPENING_MARGIN_2D):
    """
    进球判据（与单文件同构）：球心从上往下穿过 y = rim_y、vy < 0，
    且本步末的 x 落在 [xF + margin, xB - margin]（筐口内沿两侧各留余量）。

    返回 dict(entry_deg = 入筐角 [deg], x = 本步末水平位置)，否则 None。
    """
    prev = np.asarray(prev, dtype=float)
    nxt = np.asarray(nxt, dtype=float)
    if not (prev[1] > rim_y and nxt[1] <= rim_y and nxt[3] < 0.0):
        return None
    lo = float(xF) + float(opening_margin)
    hi = float(xB) - float(opening_margin)
    if not (lo < nxt[0] < hi):
        return None
    return dict(entry_deg=math.degrees(math.atan2(abs(nxt[3]), abs(nxt[2]))),
                x=float(nxt[0]))


def classify_outcome_2d(board_contact: bool, edge_contact: bool):
    """
    根据碰撞历史给出进球子类：从未碰板碰筐 -> SWISH；只碰板 -> BANK-IN；
    碰过筐（可能也碰板）-> RATTLE-IN。
    """
    if board_contact and not edge_contact:
        return "BANK-IN"
    if edge_contact:
        return "RATTLE-IN"
    return "SWISH"


MADE_OUTCOMES_2D = ("SWISH", "BANK-IN", "RATTLE-IN")

# 2D 结局名 -> 3D 主流程 / 报告使用的规范子类（大小写、连字符均一致）
OUTCOME_TO_CANONICAL_2D = {
    "SWISH": "swish",
    "BANK-IN": "board-in",
    "RATTLE-IN": "rim-in",
}


def canonical_outcome_2d(outcome):
    """把 2D 模拟器结局（SWISH/BANK-IN/RATTLE-IN 或各种 miss 描述）归一化到
    swish / board-in / rim-in / miss，供验证与图表复用。"""
    return OUTCOME_TO_CANONICAL_2D.get(str(outcome).strip().upper(), "miss")


# ---------------------------------------------------------------------------
# 快速自检 (直接运行: python collision.py)
# ---------------------------------------------------------------------------
def _show(title, pos, vel, collision, restitution=None,
          tangential_retention=TANGENTIAL_RETENTION):
    print(f"\n【{title}】")
    print(f"  碰撞前 pos = {np.asarray(pos)}; vel = {np.asarray(vel)}")
    if collision is None:
        print("  -> 未碰撞")
        return
    new_pos, new_vel = resolve(
        pos, vel, collision, restitution=restitution,
        tangential_retention=tangential_retention,
    )
    print(f"  类型={collision.kind}, 法向={collision.normal}, 嵌入深度={collision.penetration:.4f} m")
    print(f"  碰撞后 pos={new_pos}; vel={new_vel}")


def run_tests():
    """Small manual demonstration of the main contact cases."""
    _show("篮板正面", [-0.10, 3.20, 0.0], [5.0, -2.0, 0.0],
          detect_backboard([-0.10, 3.20, 0.0]))
    _show("篮筐边缘", [-0.60, 3.15, 0.0], [1.0, -3.0, 0.0],
          detect_rim([-0.60, 3.15, 0.0]))
    _show("从篮板边缘擦过", [-0.05, 2.85, 0.0], [2.0, 1.0, 0.0],
          detect_backboard([-0.05, 2.85, 0.0]))
    _show("篮筐中心轴线", RIM_CENTER + [0.0, 0.0, 0.0], [0.0, -3.0, 0.0],
          detect_rim(RIM_CENTER))


def run_tests_2d():
    """2D 模型的几何与反弹示例（与 basketball_shot_2d.py 同源）。"""
    print("\n" + "=" * 70)
    print("2D 碰撞自检（板面穿越触发 + 前后缘圆点，法向 0.70 / 切向 0.85）")
    print("=" * 70)
    xF, xB, xbc = hoop_geometry_2d(FREE_THROW_2D)
    print(f"罚球筐心 4.60 m -> xF = {xF:.4f} m, xB = {xB:.4f} m, 板参考面 xbc = {xbc:.4f} m")
    print(f"板面接触高度窗口 = [{BOARD_CONTACT_BOTTOM_2D:.2f}, {BOARD_CONTACT_TOP_2D:.2f}] m")
    print(f"筐口内沿余量 = {OPENING_MARGIN_2D * 1000:.0f} mm")

    # 1) 擦板而过：本步末已在板后，且高度在窗口外 -> 不应反弹
    prev = np.array([xbc - 0.02, 4.20, 6.0, 1.0])
    nxt = np.array([xbc + 0.02, 4.19, 5.9, 0.5])
    print("\n【擦板而过（高度在板面窗口上方）】 ->",
          "反弹" if bounce_off_board_2d(prev, nxt, xbc, 0.5) else "不反弹，继续飞")

    # 2) 实际穿过板面且在窗口内 -> 法向反转乘 0.70，切向保留乘 0.85
    prev = np.array([xbc - 0.02, 3.20, 5.0, -2.0])
    nxt = np.array([xbc + 0.02, 3.19, 4.9, -2.1])
    out = bounce_off_board_2d(prev, nxt, xbc, 0.6)
    if out:
        st, ct = out
        print(f"【正面打板】  t={ct['t']:.2f}s at ({ct['x']:.2f},{ct['y']:.2f}) "
              f"face={ct['face']}")
        print(f"  v in  ({ct['tin'][0]:.2f},{ct['tin'][1]:.2f}) -> "
              f"v out ({ct['tout'][0]:.2f},{ct['tout'][1]:.2f})")
        print(f"  状态已放到板面 x={st[0]:.4f} m（去穿透），vx -> -EN*vx, vy -> ET*vy")

    # 3) 筐沿前缘：法向分量反转乘 0.70、切向保留乘 0.85，球心被推出接触面
    st = np.array([xF - 0.05, 3.10, 4.0, -3.0])
    out = bounce_off_rim_edge_2d(st, xF, 0.8)
    if out:
        st2, ct = out
        dd, pen, _ = rim_edge_gap_2d(st, xF)
        print(f"\n【碰前筐沿 {ct['edge']} 侧】  tin={ct['tin']} -> tout={ct['tout']}")
        print(f"  球心被推出 {pen:.4f} m，新位置 ({st2[0]:.4f},{st2[1]:.4f})，"
              f"新位置到端点距离 = {math.hypot(st2[0]-xF, st2[1]-RIM_HEIGHT_2D):.4f} m（= 球半径，已相切）")

    # 4) 已在离开接触面（法向速度向外）-> 不应二次触发
    st = np.array([xF + 0.05, 3.10, 4.0, -1.0])
    print("\n【已离开筐沿（法向速度向外）】 ->",
          "反弹" if bounce_off_rim_edge_2d(st, xF, 0.9) else "不反弹，继续下落")

    # 5) 进球判据
    prev = np.array([4.55, 3.10, 5.0, -1.5])
    nxt = np.array([4.60, 3.02, 4.9, -2.0])
    sc = detect_scoring_cross_2d(prev, nxt, xF, xB)
    print("\n【空心穿筐】 ->", f"入筐角 {sc['entry_deg']:.1f}°" if sc else "未穿筐")
    print("【结局分类】 碰板未碰筐 =", classify_outcome_2d(True, False),
          "; 碰过筐 =", classify_outcome_2d(True, True),
          "; 均未碰 =", classify_outcome_2d(False, False))
    print("归一化到 3D 子类： SWISH->swish, BANK-IN->board-in, RATTLE-IN->rim-in")
    print("完整碰撞循环在 simulation.simulate_2d()。")


if __name__ == "__main__":
    run_tests()
    run_tests_2d()
