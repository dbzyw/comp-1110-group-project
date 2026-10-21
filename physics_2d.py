"""2D-only physics model for the interactive demo and modelling comparisons.

This file contains the deck-frozen 2D constants and the 2D motion equations.
The 3D main pipeline remains in physics.py and intentionally uses a different
set of constants; the two models are kept separate to avoid cross-contamination.
"""

import math

import numpy as np

# Deck-frozen 2D constants from the single-file simulator.
BALL_RADIUS_2D = 0.12
BALL_MASS_2D = 0.60
RHO_AIR_2D = 1.204
C_D_2D = 0.47
C_L_2D = 0.20
BALL_AREA_2D = math.pi * BALL_RADIUS_2D ** 2

DRAG_PARAM_2D = 0.5 * RHO_AIR_2D * C_D_2D * BALL_AREA_2D / BALL_MASS_2D
MAGNUS_PARAM_2D = 0.5 * RHO_AIR_2D * C_L_2D * BALL_AREA_2D * BALL_RADIUS_2D / BALL_MASS_2D

RIM_HEIGHT_2D = 3.05
RIM_RADIUS_2D = 0.2287
BOARD_OFFSET_2D = 0.15
FREE_THROW_2D = 4.60
THREE_POINT_2D = 6.75
RELEASE_FLOOR_2D = 0.10

RESTITUTION_NORMAL_2D = 0.70
RESTITUTION_TANGENTIAL_2D = 0.85
G_2D = 9.81


def release_velocity(speed: float, angle_deg: float, azimuth_deg: float = 0.0) -> np.ndarray:
    """Create a 3D release velocity from a scalar speed and elevation angle."""
    if speed < 0.0:
        raise ValueError(f"speed must be non-negative, got {speed!r}")
    ang = np.deg2rad(angle_deg)
    az = np.deg2rad(azimuth_deg)
    vx = speed * np.cos(ang) * np.cos(az)
    vy = speed * np.sin(ang)
    vz = speed * np.cos(ang) * np.sin(az)
    return np.array([vx, vy, vz])


def spin_in_plane_2d(spin_rate: float, angle_deg: float) -> float:
    """Return the in-plane spin component omega_z = spin * sin(theta)."""
    return float(spin_rate) * math.sin(math.radians(float(angle_deg)))


def acceleration_2d(vx: float, vy: float, spin_z: float, air: bool = True):
    """2D acceleration: gravity + drag + Magnus lift."""
    kd = DRAG_PARAM_2D if air else 0.0
    km = MAGNUS_PARAM_2D if air else 0.0
    speed = math.hypot(vx, vy)
    ax = -kd * speed * vx + km * spin_z * vy
    ay = -G_2D - kd * speed * vy - km * spin_z * vx
    return ax, ay


def derivatives_2d(state, spin_z: float, air: bool = True) -> np.ndarray:
    """State derivative for [x, y, vx, vy]."""
    vx, vy = state[2], state[3]
    ax, ay = acceleration_2d(vx, vy, spin_z, air)
    return np.array([vx, vy, ax, ay])


def rk4_step_2d(state, dt: float, spin_z: float, air: bool = True) -> np.ndarray:
    """One-step RK4 update for a 2D state."""
    k1 = derivatives_2d(state, spin_z, air)
    k2 = derivatives_2d(state + 0.5 * dt * k1, spin_z, air)
    k3 = derivatives_2d(state + 0.5 * dt * k2, spin_z, air)
    k4 = derivatives_2d(state + dt * k3, spin_z, air)
    return state + dt / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def ideal_arc_coeffs_2d(h0: float, angle_deg: float, v: float):
    """Return slope and curvature for the ideal parabolic arc."""
    th = math.radians(angle_deg)
    c = math.cos(th)
    return math.tan(th), G_2D / (2.0 * v * v * c * c)


def ideal_parabola_2d(h0: float, angle_deg: float, v: float, n: int = 400):
    """Vacuum parabolic trajectory with standard landing threshold at 0.10 m."""
    slope, a2 = ideal_arc_coeffs_2d(h0, angle_deg, v)
    b = h0 - RELEASE_FLOOR_2D
    x_land = (slope + math.sqrt(slope * slope + 4.0 * a2 * b)) / (2.0 * a2)
    xs = np.linspace(0.0, x_land, n)
    return xs, h0 + slope * xs - a2 * xs * xs, slope, a2, x_land


def vacuum_aim_2d(h0: float, angle_deg: float, dist: float,
                  rim_height: float = RIM_HEIGHT_2D):
    """Vacuum launch speed required to reach the rim height at a given distance."""
    th = math.radians(angle_deg)
    rhs = h0 + dist * math.tan(th) - rim_height
    if rhs <= 0:
        return None
    v = math.sqrt(0.5 * G_2D * dist * dist / (rhs * math.cos(th) ** 2))
    return v, rhs


def air_load_2d(v: float, spin_rate: float, angle_deg: float):
    """Return the drag and Magnus loading at launch."""
    wz = spin_in_plane_2d(spin_rate, angle_deg)
    return DRAG_PARAM_2D * v * v, MAGNUS_PARAM_2D * abs(wz) * v, wz


def curvature_flatten_pct_2d(h0: float, angle_deg: float, v: float,
                             fitted_a2: float) -> float | None:
    """Percent flattening relative to the ideal vacuum parabola."""
    _, a2_i = ideal_arc_coeffs_2d(h0, angle_deg, v)
    if abs(fitted_a2) <= 1e-6:
        return None
    return (abs(a2_i) - abs(fitted_a2)) / abs(a2_i) * 100.0
