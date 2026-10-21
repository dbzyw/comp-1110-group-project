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


if __name__ == "__main__":
    run_tests()
