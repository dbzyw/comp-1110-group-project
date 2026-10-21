"""2D-only collision model for the interactive basketball demo.

The 2D model uses a planar board and rim-edge contact model, with a different
restitution scheme from the 3D pipeline in collision.py.
"""

import math

import numpy as np

from physics_2d import BALL_RADIUS_2D, RIM_HEIGHT_2D, RIM_RADIUS_2D, BOARD_OFFSET_2D

BOARD_CONTACT_BOTTOM_2D = RIM_HEIGHT_2D - 0.30
BOARD_CONTACT_TOP_2D = RIM_HEIGHT_2D + 0.80
BOARD_CONTACT_WINDOW_2D = (BOARD_CONTACT_BOTTOM_2D, BOARD_CONTACT_TOP_2D)
OPENING_MARGIN_2D = 0.012
MAX_BOARD_BOUNCES_2D = 4

RESTITUTION_NORMAL_2D = 0.70
RESTITUTION_TANGENTIAL_2D = 0.85
FREE_THROW_2D = 4.60


def hoop_geometry_2d(center_x: float, *, rim_radius: float = RIM_RADIUS_2D,
                     ball_radius: float = BALL_RADIUS_2D,
                     board_offset: float = BOARD_OFFSET_2D):
    """Return the front edge, rear edge and board-contact reference x-position."""
    c = float(center_x)
    xF = c - rim_radius
    xB = c + rim_radius
    return xF, xB, xB + board_offset - ball_radius


def reflect_2d(vx: float, vy: float, nx: float, ny: float,
               e_n: float = RESTITUTION_NORMAL_2D,
               e_t: float = RESTITUTION_TANGENTIAL_2D):
    """Reflect a 2D velocity vector across a contact normal."""
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
    """Check whether the ball crossed the board plane in this integration step."""
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
    """Trigger a board bounce when the ball crosses the plane in-range."""
    info = cross_board_plane_2d(prev, nxt, board_x, height_window)
    if info is None:
        return None
    nx = -1.0 if info["vx"] > 0.0 else 1.0
    vxr, vyr = reflect_2d(info["vx"], info["vy"], nx, 0.0, e_n, e_t)
    state = np.array([info["x"], info["y"], vxr, vyr], dtype=float)
    contact = dict(kind="board", t=float(t_contact), x=float(info["x"]),
                   y=float(info["y"]), tin=(info["vx"], info["vy"]),
                   tout=(vxr, vyr), face="front" if info["vx"] > 0 else "back")
    return state, contact


def rim_edge_gap_2d(state, edge_x: float, *, rim_y: float = RIM_HEIGHT_2D,
                    ball_radius: float = BALL_RADIUS_2D):
    """Distance from the state to the rim edge used as a point contact."""
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
    """List rim-edge overlaps at the front and rear contact points."""
    out = []
    for xe in (float(xF), float(xB)):
        dd, pen, normal = rim_edge_gap_2d(state, xe, rim_y=rim_y, ball_radius=ball_radius)
        if pen > 0.0 and dd > 1e-9:
            out.append((xe, dd, pen, normal))
    return out


def bounce_off_rim_edge_2d(state, edge_x: float, t_contact: float, *,
                           rim_y: float = RIM_HEIGHT_2D,
                           ball_radius: float = BALL_RADIUS_2D,
                           e_n: float = RESTITUTION_NORMAL_2D,
                           e_t: float = RESTITUTION_TANGENTIAL_2D):
    """Apply a rim-edge reflection when incoming normal velocity is inward."""
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
    """Return the score-detection data when the ball passes downward through the rim plane."""
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
    """Classify the 2D result into board or rim outcomes."""
    if board_contact and not edge_contact:
        return "BANK-IN"
    if edge_contact:
        return "RATTLE-IN"
    return "SWISH"


MADE_OUTCOMES_2D = ("SWISH", "BANK-IN", "RATTLE-IN")
OUTCOME_TO_CANONICAL_2D = {
    "SWISH": "swish",
    "BANK-IN": "board-in",
    "RATTLE-IN": "rim-in",
}


def canonical_outcome_2d(outcome):
    """Normalize 2D outcome strings to the 3D canonical categories."""
    return OUTCOME_TO_CANONICAL_2D.get(str(outcome).strip().upper(), "miss")
