"""2D-only shot simulation pipeline.

This file is intentionally separate from the 3D pipeline in simulation.py so the
2D demo constants and the 3D experimental constants do not get mixed.
"""

import math

import numpy as np

from collision_2d import (
    bounce_off_board_2d,
    bounce_off_rim_edge_2d,
    classify_outcome_2d,
    detect_scoring_cross_2d,
    hoop_geometry_2d,
    MADE_OUTCOMES_2D,
    MAX_BOARD_BOUNCES_2D,
    OPENING_MARGIN_2D,
)
from physics_2d import (
    BALL_RADIUS_2D,
    DRAG_PARAM_2D,
    FREE_THROW_2D,
    G_2D,
    MAGNUS_PARAM_2D,
    RELEASE_FLOOR_2D,
    RIM_HEIGHT_2D,
    air_load_2d,
    curvature_flatten_pct_2d,
    rk4_step_2d,
    spin_in_plane_2d,
    vacuum_aim_2d,
)


def simulate_2d(h0: float, angle_deg: float, spin: float, v: float, dist: float,
                *, air: bool = True, max_t: float = 4.0, dt: float = 1e-3,
                max_board_bounces: int = MAX_BOARD_BOUNCES_2D,
                opening_margin: float = OPENING_MARGIN_2D):
    """2D single-shot simulation for the interactive demo."""
    th = math.radians(angle_deg)
    wz = spin * math.sin(th)
    xF, xB, xbc = hoop_geometry_2d(dist)

    s = np.array([0.0, h0, v * math.cos(th), v * math.sin(th)])
    T = [0.0]
    X = [s[0]]
    Y = [s[1]]
    VX = [s[2]]
    VY = [s[3]]
    t = 0.0
    board = False
    hits = 0
    edge = 0
    outcome = "in flight"
    entry = None
    plane_h = None
    peak = h0
    contacts = []

    def record(sx, sy, svx, svy):
        T.append(t)
        X.append(float(sx))
        Y.append(float(sy))
        VX.append(float(svx))
        VY.append(float(svy))

    for _ in range(int(max_t / dt)):
        s2 = rk4_step_2d(s, dt, wz, air=air)

        if s2[1] > peak:
            peak = float(s2[1])

        if plane_h is None and s[0] < dist <= s2[0]:
            w = (dist - s[0]) / (s2[0] - s[0])
            plane_h = float(s[1] + w * (s2[1] - s[1]))

        if hits < max_board_bounces:
            out = bounce_off_board_2d(s, s2, xbc, t + dt)
            if out is not None:
                s2, ct = out
                hits += 1
                board = True
                contacts.append(ct)

        for xe in (xF, xB):
            out = bounce_off_rim_edge_2d(s2, xe, t + dt)
            if out is not None:
                s2, ct = out
                edge += 1
                contacts.append(ct)

        score = detect_scoring_cross_2d(s, s2, xF, xB, opening_margin=opening_margin)
        if score is not None:
            entry = float(score["entry_deg"])
            outcome = classify_outcome_2d(board, edge != 0)
            t += dt
            record(s2[0], s2[1], s2[2], s2[3])
            break

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
    """Split a 2D trajectory into single-valued x-branches and fit quadratics."""
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
        if xs[-1] < xs[0]:
            xs, ys = xs[::-1], ys[::-1]
        a2, a1, a0 = np.polyfit(xs, ys, 2)
        segs.append(dict(a2=float(a2), a1=float(a1), a0=float(a0),
                         x0=float(xs[0]), x1=float(xs[-1]),
                         after=bool(cuts[i] > 0.001)))
    return segs


def save_2d_csv(path, res):
    """Save a 2D simulation as time,x,y,vx,vy CSV."""
    data = np.column_stack((res["T"], res["X"], res["Y"], res["VX"], res["VY"]))
    np.savetxt(path, data, delimiter=",",
               header="time,x,y,vx,vy", comments="", fmt="%.6f")


def readout_2d(res, h0: float, angle_deg: float, spin: float, v: float, dist: float):
    """Summarize the 2D result into a compact report dict."""
    from collision_2d import canonical_outcome_2d
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
