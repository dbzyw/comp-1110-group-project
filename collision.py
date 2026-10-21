"""Basketball collision detection and response for a rectangular backboard and rim.

Coordinates use SI units: x points from the shooter towards the hoop, y is up,
and z is lateral.  The backboard is a finite, zero-thickness rectangle at x=0;
the rim is a thin horizontal circle.  Contact response uses a frictionless,
constant-coefficient-of-restitution model.
"""

from dataclasses import dataclass

import numpy as np

try:
    from physics import BALL_RADIUS
except ImportError:  # Keep this module usable by itself for demonstrations/tests.
    BALL_RADIUS = 0.12


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
RESTITUTION = 0.7


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


def detect_backboard(pos) -> Collision | None:
    """Detect a sphere touching the finite rectangular backboard.

    The nearest point on the rectangle is used, so edge and corner contacts are
    included (unlike an infinite-plane test clipped by the ball-centre bounds).
    """
    center = _vector3(pos, "pos")
    contact = np.array([
        BACKBOARD_X,
        np.clip(center[1], BACKBOARD_BOTTOM, BACKBOARD_TOP),
        np.clip(center[2], -BACKBOARD_HALF_WIDTH, BACKBOARD_HALF_WIDTH),
    ])
    delta = center - contact
    distance = float(np.linalg.norm(delta))
    penetration = BALL_RADIUS - distance
    if penetration < 0.0:
        return None

    if distance > 1e-12:
        normal = delta / distance
    else:
        # The centre lies on the ideal zero-thickness board; choose a stable side.
        normal = np.array([-1.0, 0.0, 0.0] if center[0] < BACKBOARD_X
                          else [1.0, 0.0, 0.0])
    return Collision("backboard", normal, penetration, contact)


def detect_rim(pos) -> Collision | None:
    """Detect sphere contact with the thin horizontal circular rim."""
    center = _vector3(pos, "pos")
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
    penetration = BALL_RADIUS - distance
    if penetration < 0.0:
        return None

    # For the project's dimensions distance cannot be zero, but keep the normal
    # well-defined if dimensions are changed in a future version.
    if distance > 1e-12:
        normal = delta / distance
    else:
        normal = np.array([1.0, 0.0, 0.0])
    return Collision("rim", normal, penetration, contact)


def detect_any(pos) -> Collision | None:
    """Return a backboard contact first, otherwise a rim contact."""
    collision = detect_backboard(pos)
    return collision if collision is not None else detect_rim(pos)


def detect_backboard_batch(pos):
    """Vectorised rectangular-board test; returns hit, normal, penetration."""
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
    penetration = BALL_RADIUS - distance
    hit = penetration >= 0.0

    normals = np.zeros_like(centers)
    nonzero = hit & (distance > 1e-12)
    normals[nonzero] = delta[nonzero] / distance[nonzero, None]
    centered = hit & ~nonzero
    normals[centered, 0] = np.where(centers[centered, 0] < BACKBOARD_X, -1.0, 1.0)
    return hit, normals, penetration


def detect_rim_batch(pos):
    """Vectorised rim test; returns hit, normal, penetration."""
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
    penetration = BALL_RADIUS - distance
    hit = penetration >= 0.0

    normals = np.zeros_like(centers)
    nonzero = hit & (distance > 1e-12)
    normals[nonzero] = delta[nonzero] / distance[nonzero, None]
    normals[hit & ~nonzero, 0] = 1.0
    return hit, normals, penetration


def reflect(vel, normal, e: float = RESTITUTION) -> np.ndarray:
    """Reflect approaching velocity using restitution e; tangential speed stays.

    With outward unit normal n and incoming normal speed v_n = v·n < 0,
    v_after = v_before - (1+e) v_n n.  Separating contacts are unchanged.
    """
    velocity = _vector3(vel, "vel")
    normal = _vector3(normal, "normal")
    norm = float(np.linalg.norm(normal))
    if not np.isclose(norm, 1.0, atol=1e-8):
        raise ValueError("normal must be a unit vector")
    if not np.isfinite(e) or not 0.0 <= e <= 1.0:
        raise ValueError("e must be between 0 and 1")

    normal_speed = float(np.dot(velocity, normal))
    if normal_speed < 0.0:
        velocity = velocity - (1.0 + e) * normal_speed * normal
    return velocity


def resolve(pos, vel, collision: Collision, correct_position: bool = True):
    """Apply the frictionless bounce and optionally remove geometric overlap."""
    position = _vector3(pos, "pos").copy()
    velocity = reflect(vel, collision.normal, RESTITUTION)
    if correct_position and collision.penetration > 0.0:
        position += collision.normal * collision.penetration
    return position, velocity


def _show(title, pos, vel, collision):
    print(f"\n【{title}】")
    print(f"  碰撞前 pos = {np.asarray(pos)}; vel = {np.asarray(vel)}")
    if collision is None:
        print("  -> 未碰撞")
        return
    new_pos, new_vel = resolve(pos, vel, collision)
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


if __name__ == "__main__":
    run_tests()
