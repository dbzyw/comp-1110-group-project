"""
basketball_shot_2d_improved.py — basketball_shot_2d.py 的改进版（原文件保留）

与原版同一个 Tkinter 交互器、同一套冻结常数 (COMP1110 deck)、同一个逐步
simulate 循环 —— 任何有效输入下 `simulate` / `fit_segments` / `find_band`
的数值与原版逐位一致 (test_core 的 UI 复现基准就是原版)。
本版本只做了三件事:

    * 模块文档 (原版连开头的 docstring 都没有)
    * 入口校验: ideal_parabola 拒绝 v<=0 (原版 ZeroDivisionError);
      simulate 拒绝非有限参数; find_band 拒绝 steps<2 —— 全部只拦截
      “本来就会崩/静默变 NaN”的输入，有效输入行为不变
    * `python basketball_shot_2d_improved.py --check`: 无头自检模式，
      复算 6 个 DEMO_SCENES 并对照原版 simulate (不弹窗口，供 CI 使用);
      默认仍是 `main()` 交互器，与原版相同

用法:
    python basketball_shot_2d_improved.py            # 打开交互器 (同原版)
    python basketball_shot_2d_improved.py --check    # 无头逐位自检
"""

import math
import sys
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
from matplotlib.widgets import Slider, Button
from matplotlib.animation import FuncAnimation

# ============ frozen model constants (COMP1110 deck) ============
R = 0.12; M = 0.60; AREA = math.pi * R * R
RHO = 1.204; CD = 0.47; CL = 0.20; GRAV = 9.81
EN = 0.70; ET = 0.85
YR = 3.05; RIM_R = 0.2287; BOARD_OFF = 0.15
FT_DIST = 4.60; PT_DIST = 6.75
BD = 0.5 * RHO * CD * AREA / M      # 0.02134 /m  drag
BM = 0.5 * RHO * CL * AREA * R / M  # 1.0895e-3   Magnus

# ============ UI palette ============
BG      = "#111722"
PANEL   = "#1B2430"
GRID    = "#263042"
BTN     = "#33405A"
INK     = "#F0F4F8"
MUTED   = "#93A0AF"
ACCENT  = "#D9642E"      # ball / rim
GOOD    = "#4FBF7F"
BAD     = "#FF6B6B"
NAVY    = "#4A7FC1"      # RK4 flight
TEAL    = "#3FC8C8"      # collision-aware fitted arc
VIOLET  = "#9A7CD8"      # ideal no-air parabola
BOARD_C = "#7FA8CC"

DEG = "°"

# 与 SIMULATION_2D_DEMOS.md / simulation.py __main__ 相同的 6 个典型场景
# (name, h0, angle, spin, v, dist, air, expected outcome)
DEMO_SCENES = [
    ("01_free_throw_swish", 2.00, 51.0, 23.0, 7.90, FT_DIST, True,  "SWISH"),
    ("02_bank_shot",        2.00, 36.0, 23.0, 9.10, FT_DIST, True,  "BANK-IN"),
    ("03_rattle_in",        2.00, 36.0, 23.0, 8.70, FT_DIST, True,  "RATTLE-IN"),
    ("04_short_miss",       2.00, 51.0, 23.0, 6.00, FT_DIST, True,  "well short"),
    ("05_air_off",          2.00, 51.0, 23.0, 7.90, FT_DIST, False, "BANK-IN"),
    ("06_three_pointer",    2.00, 45.0, 23.0, 9.46, PT_DIST, True,  "SWISH"),
]


def _finite(name, value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return value


def hoop_geoms(center):
    xF = center - RIM_R
    xB = center + RIM_R
    return xF, xB, xB + BOARD_OFF - R


def ideal_parabola(h0, angle_deg, v):
    """no-air y(x): y = h0 + x tan(th) - g x^2 / (2 v^2 cos^2(th))

    改进版: v <= 0 显式 ValueError (原版直接 ZeroDivisionError)。
    """
    v = _finite("v", v)
    if v <= 0.0:
        raise ValueError(f"v must be positive, got {v!r}")
    th = math.radians(angle_deg)
    c = math.cos(th)
    if abs(c) < 1e-12:
        raise ValueError(f"angle_deg={angle_deg!r} is vertical; no finite a2")
    slope = math.tan(th)
    a2 = GRAV / (2 * v * v * c * c)
    b = h0 - 0.10
    disc = slope * slope + 4 * a2 * b
    if disc < 0.0:
        raise ValueError(
            f"no landing root for h0={h0!r} angle={angle_deg!r} v={v!r} "
            f"(disc={disc:.3e} < 0)")
    x_land = (slope + math.sqrt(disc)) / (2 * a2)
    xs = np.linspace(0.0, x_land, 400)
    return xs, h0 + slope * xs - a2 * xs * xs, slope, a2, x_land


def simulate(h0, angle_deg, spin, v, dist, air=True, max_t=4.0, dt=1e-3):
    """一步一帧的 2D RK4 + 板面穿越 + 前后缘反弹 + 穿筐判定 (与原版逐位一致)。

    改进版只在入口处拒绝非有限参数; 循环体、判据、结局串与原版完全相同。
    """
    h0 = _finite("h0", h0); angle_deg = _finite("angle_deg", angle_deg)
    spin = _finite("spin", spin); v = _finite("v", v); dist = _finite("dist", dist)
    max_t = _finite("max_t", max_t); dt = _finite("dt", dt)
    if dt <= 0.0:
        raise ValueError(f"dt must be positive, got {dt!r}")
    th = math.radians(angle_deg)
    wz = spin * math.sin(th)
    kd = BD if air else 0.0
    km = BM if air else 0.0
    xF, xB, xbc = hoop_geoms(dist)
    s = np.array([0.0, h0, v * math.cos(th), v * math.sin(th)])
    T = [0.0]; X = [s[0]]; Y = [s[1]]; t = 0.0
    board = False; hits = 0; edge = 0
    outcome = "in flight"; entry = None; plane_h = None; peak = h0
    contacts = []
    def dv(s_):
        vx, vy = s_[2], s_[3]; sp = math.hypot(vx, vy)
        return np.array([vx, vy,
                         -kd * sp * vx + km * wz * vy,
                         -GRAV - kd * sp * vy - km * wz * vx])
    for _ in range(int(max_t / dt)):
        k1 = dv(s)
        k2 = dv(s + 0.5 * dt * k1)
        k3 = dv(s + 0.5 * dt * k2)
        k4 = dv(s + dt * k3)
        s2 = s + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        if s2[1] > peak: peak = s2[1]
        if plane_h is None and s[0] < dist <= s2[0]:
            w = (dist - s[0]) / (s2[0] - s[0])
            plane_h = s[1] + w * (s2[1] - s[1])
        # backboard bounce, front or back face: fires only when the ball
        # actually crosses the board plane inside this step, so a shot that
        # clears the glass keeps flying behind it instead of teleporting back
        # onto the board from metres away
        if hits < 4 and (s[0] - xbc) * (s2[0] - xbc) < 0:
            w = (xbc - s[0]) / (s2[0] - s[0])
            yc = s[1] + w * (s2[1] - s[1])
            vxc = s[2] + w * (s2[2] - s[2])
            vyc = s[3] + w * (s2[3] - s[3])
            if (YR - 0.30) <= yc <= (YR + 0.80):
                hits += 1; board = True
                tin = (vxc, vyc)
                s2 = np.array([xbc, yc, -EN * vxc, ET * vyc])
                contacts.append(dict(kind="board", t=t + dt, x=xbc, y=yc,
                                     tin=tin, tout=(s2[2], s2[3]),
                                     face="front" if vxc > 0 else "back"))
        # rim wire bounces, front and back edges
        for xe in (xF, xB):
            dx = s2[0] - xe; dy = s2[1] - YR
            dd = math.hypot(dx, dy)
            if dd < R and dd > 1e-9:
                nx, ny = dx / dd, dy / dd
                vdn = s2[2] * nx + s2[3] * ny
                if vdn < 0:
                    edge += 1
                    tin = (s2[2], s2[3])
                    vtx = s2[2] - vdn * nx; vty = s2[3] - vdn * ny
                    s2 = np.array([s2[0] + (R - dd) * nx, s2[1] + (R - dd) * ny,
                                   ET * vtx - EN * vdn * nx, ET * vty - EN * vdn * ny])
                    contacts.append(dict(kind="rim", t=t + dt, x=float(xe),
                                         y=float(YR), tin=tin,
                                         tout=(s2[2], s2[3]), edge=dx > 0 and "back" or "front"))
        # ball centre drops through the opening
        if s[1] > YR and s2[1] <= YR and s2[3] < 0 and (xF + 0.012) < s2[0] < (xB - 0.012):
            entry = math.degrees(math.atan2(abs(s2[3]), abs(s2[2])))
            if not board and edge == 0: outcome = "SWISH"
            elif board and edge == 0:   outcome = "BANK-IN"
            else:                        outcome = "RATTLE-IN"
            t += dt
            T.append(t); X.append(s2[0]); Y.append(s2[1])
            break
        if s2[1] < 0.10:
            if board:       outcome = "off the board, out"
            elif edge:      outcome = "off the rim, out"
            elif max(X) > xbc + 0.02:
                outcome = "past the board, lands behind"
            elif plane_h is not None and plane_h < YR:
                outcome = "long miss, past the hoop"
            elif plane_h is not None:
                outcome = "short, low at the rim plane"
            else:
                outcome = "well short"
            t += dt
            T.append(t); X.append(s2[0]); Y.append(s2[1])
            break
        t += dt
        T.append(t); X.append(s2[0]); Y.append(s2[1]); s = s2
    made = outcome in ("SWISH", "BANK-IN", "RATTLE-IN")
    return dict(T=np.array(T), X=np.array(X), Y=np.array(Y), outcome=outcome,
                made=made, entry=entry, plane_h=plane_h, peak=peak,
                board=board, hits=hits, edge=edge, xF=xF, xB=xB, xbc=xbc,
                flight=t, air=air, contacts=contacts)


def fit_segments(res):
    """piecewise quadratic y(x) fitted to the FULL RK4 flight, split at the
    board collision and at every horizontal direction reversal (rim / board
    rebounds) so each fitted branch is a single-valued y(x).  The coefficients
    therefore carry air drag, spin lift and every bounce, including the
    reverse branch behind the backboard."""
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
        xs = X[m]; ys = Y[m]
        # each branch is monotonic in x now; flip so the fit runs forward
        if xs[-1] < xs[0]:
            xs, ys = xs[::-1], ys[::-1]
        a2, a1, a0 = np.polyfit(xs, ys, 2)
        segs.append(dict(a2=float(a2), a1=float(a1), a0=float(a0),
                         x0=float(xs[0]), x1=float(xs[-1]),
                         after=bool(cuts[i] > 0.001)))
    return segs


def vacuum_aim(h0, angle_deg, dist):
    th = math.radians(angle_deg)
    rhs = h0 + dist * math.tan(th) - YR
    if rhs <= 0: return None
    c2 = math.cos(th) ** 2
    if c2 < 1e-24: return None      # 改进版: 垂直仰角下“水平射程”无解 (同 vacuum_aim_2d)
    v = math.sqrt(0.5 * GRAV * dist * dist / (rhs * c2))
    return v, rhs


def find_band(h0, angle_deg, spin, dist, want="made", air=True, steps=150):
    """最宽连续命中速度区段 (与 experiment.find_band_2d / UI SCAN WINDOW 同规则)。

    改进版: steps < 2 显式 ValueError。
    """
    steps = int(steps)
    if steps < 2:
        raise ValueError(f"steps must be >= 2, got {steps!r}")
    vs = np.linspace(5.5, 14.5, steps)
    recs = [simulate(h0, angle_deg, spin, float(vv), dist, air=air) for vv in vs]
    flags = ([r["made"] for r in recs] if want == "made"
             else [r["outcome"] == want.upper() for r in recs])
    runs = []; i = 0
    while i < len(flags):
        if flags[i]:
            j = i
            while j + 1 < len(flags) and flags[j + 1]: j += 1
            runs.append((i, j)); i = j + 1
        else:
            i += 1
    if not runs: return None
    lo_i, hi_i = max(runs, key=lambda a: a[1] - a[0])
    mid_i = (lo_i + hi_i) // 2
    for k in range(mid_i, lo_i - 1, -1):
        if flags[k]: mid_i = k; break
    return float(vs[lo_i]), float(vs[hi_i]), float(vs[mid_i]), recs[mid_i]["outcome"]


# ============ scene: artists are created ONCE and updated in place ============
# every slider drag used to ax.plot brand-new curves on top of the old ones;
# now init_scene builds the full artist set and update_scene only mutates the
# existing artists (set_data / set_center / set_bounds), so the parabola
# deforms live with the data instead of stacking up copies.

def init_scene(ax):
    ax.set_facecolor(PANEL)
    ax.set_aspect("equal")
    ax.grid(True, color=GRID, lw=0.6)
    for sp in ax.spines.values(): sp.set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.set_xlabel("horizontal distance from the release, m", color=MUTED, fontsize=9)
    ax.set_ylabel("ball-centre height, m", color=MUTED, fontsize=9)

    A = {}
    # three fixed slots for the fitted arcs (launch / after board / reverse)
    A["fit"] = [ax.plot([], [], ls=(0, (6, 2, 1, 2)), lw=1.5, color=TEAL,
                        alpha=0.95, zorder=3)[0] for _ in range(3)]
    A["ideal"] = ax.plot([], [], ls=(0, (4, 3)), lw=1.3, color=VIOLET, zorder=2)[0]
    # court
    ax.add_patch(Rectangle((-0.8, -0.05), 10.5, 0.05, color="#33405A", zorder=1))
    A["rimguide"] = ax.plot([], [], color=MUTED, lw=0.6, ls=(0, (1, 4)),
                            alpha=0.45, zorder=2)[0]
    # backboard
    A["board"] = Rectangle((0, 0), 0.06, 1.10, facecolor=BOARD_C, edgecolor=INK,
                           lw=0.8, alpha=0.28, zorder=3)
    A["boardwin"] = Rectangle((0, 0), 0.045, 0.30, facecolor="none",
                              edgecolor="#EAF2FA", lw=1.4, alpha=0.85, zorder=4)
    ax.add_patch(A["board"]); ax.add_patch(A["boardwin"])
    # net, rim, arm
    A["net"] = [ax.plot([], [], color="#C6D2DE", lw=0.55, alpha=0.55, zorder=5)[0]
                for _ in range(7)]
    A["rim"] = ax.plot([], [], color=ACCENT, lw=3.4, zorder=6)[0]
    A["rimend"] = [Circle((0, 0), 0.018, facecolor=ACCENT, edgecolor=INK,
                          lw=0.6, zorder=7) for _ in range(2)]
    for c in A["rimend"]: ax.add_patch(c)
    A["arm"] = ax.plot([], [], color=MUTED, lw=1.2, zorder=4)[0]
    # shooter
    A["body"] = ax.plot([], [], color="#B7C4D0", lw=3.0, zorder=4)[0]
    A["head"] = Circle((0, 0), 0.10, facecolor="#B7C4D0", zorder=4)
    ax.add_patch(A["head"])
    A["arm2"] = ax.plot([], [], color="#B7C4D0", lw=2.2, zorder=4)[0]
    A["shoulder"] = ax.plot([], [], color="#B7C4D0", lw=1.2, zorder=4)[0]
    A["feet"] = ax.plot([-0.14, 0.14], [0.0, 0.0], color="#B7C4D0", lw=2.4,
                        zorder=4)[0]
    # exact RK4 flight
    A["flight"] = ax.plot([], [], lw=1.8, color=NAVY, zorder=5)[0]
    # ball with backspin seams
    A["ball"] = Circle((0, 0), R, facecolor="#E8722F", edgecolor="#F7C59A",
                       lw=1.0, zorder=8)
    ax.add_patch(A["ball"])
    A["seams"] = [ax.plot([], [], color="#8C3A12", lw=1.1, zorder=9)[0]
                  for _ in range(2)]
    # apex + contact markers
    A["apex"] = ax.plot([], [], marker="^", ms=7, color=GOOD, mec="#111722",
                        mew=0.8, ls="", zorder=7)[0]
    A["boardmark"] = ax.plot([], [], marker="o", ms=8, mfc="#FFD166",
                             mec="#8C3A12", ls="", zorder=8)[0]
    A["rimmark"] = ax.scatter([], [], s=36, marker="s", c="#FFFFFF",
                              edgecolors=ACCENT, zorder=8)
    # status strip
    A["status"] = ax.text(0.015, 0.965, "", transform=ax.transAxes, fontsize=15,
                          fontweight="bold", color=GOOD, va="top")
    A["headtxt"] = ax.text(0.015, 0.895, "", transform=ax.transAxes, fontsize=9,
                           color=MUTED, va="top")
    return A


def update_scene(ax, A, params, res, t=None, show_real=True, show_ideal=False):
    h0, ang, spin, v, dist = params
    xF, xB, xbc = res["xF"], res["xB"], res["xbc"]
    board_x = xbc + R
    segs = fit_segments(res)
    ixs, iys, slope_i, a2_i, x_land = ideal_parabola(h0, ang, v)

    top = max(4.4, res["peak"] + 0.45)
    # widen the view when the ball lands behind the backboard so the tail of
    # the trajectory is drawn instead of running off the right edge
    ax.set_xlim(-0.8, max(7.9, board_x + 0.6, float(res["X"].max()) + 0.5))
    ax.set_ylim(-0.05, top)

    # collision-aware fitted parabolas: same two artists, data swapped in place
    for k, ln in enumerate(A["fit"]):
        if show_real and k < len(segs):
            sg = segs[k]
            xx = np.linspace(sg["x0"], sg["x1"], 200)
            yy = sg["a2"] * xx * xx + sg["a1"] * xx + sg["a0"]
            ln.set_data(xx, yy)
            ln.set_visible(True)
        else:
            ln.set_data([], [])
            ln.set_visible(False)

    # ideal no-air parabola for comparison
    if show_ideal:
        m = ixs <= ax.get_xlim()[1]
        A["ideal"].set_data(ixs[m], iys[m])
        A["ideal"].set_visible(True)
    else:
        A["ideal"].set_data([], [])
        A["ideal"].set_visible(False)

    A["rimguide"].set_data([-0.8, board_x], [YR, YR])
    A["board"].set_bounds(board_x - 0.03, YR - 0.30, 0.06, 1.10)
    A["boardwin"].set_bounds(board_x - 0.05, YR - 0.05, 0.045, 0.30)
    for i, ln in enumerate(A["net"]):
        xx = xF + i * (xB - xF) / 6
        ln.set_data([xx, xx + 0.015 * math.sin(i)], [YR, YR - 0.34])
    A["rim"].set_data([xF, xB], [YR, YR])
    A["rimend"][0].set_center((xF, YR))
    A["rimend"][1].set_center((xB, YR))
    A["arm"].set_data([xB, board_x], [YR, YR])

    # shooter follows the release height
    A["body"].set_data([0.0, 0.0], [0.0, h0 - 0.14])
    A["head"].set_center((0.0, h0 - 0.03))
    A["arm2"].set_data([0.0, 0.09], [h0 - 0.38, h0 + 0.03])
    A["shoulder"].set_data([0.0, 0.06], [h0, h0 + 0.12])

    # exact RK4 flight
    if t is None:
        A["flight"].set_data(res["X"], res["Y"])
        bx, by = res["X"][0], res["Y"][0]
    else:
        msk = res["T"] <= t
        if msk.sum() > 2:
            A["flight"].set_data(res["X"][msk], res["Y"][msk])
        else:
            A["flight"].set_data([], [])
        bx = float(np.interp(t, res["T"], res["X"]))
        by = float(np.interp(t, res["T"], res["Y"]))

    # ball with backspin seams
    A["ball"].set_center((bx, by))
    wz = spin * math.sin(math.radians(ang))
    phi = wz * (t if t is not None else 0.0)
    for k, ln in enumerate(A["seams"]):
        a0 = phi + k * math.pi / 2
        dx = R * 0.85 * math.cos(a0); dy = R * 0.85 * math.sin(a0)
        ln.set_data([bx - dx, bx + dx], [by - dy, by + dy])

    i_apex = int(np.argmax(res["Y"]))
    A["apex"].set_data([res["X"][i_apex]], [res["Y"][i_apex]])
    bct = [c for c in res["contacts"] if c["kind"] == "board"]
    if bct:
        A["boardmark"].set_data([bct[0]["x"]], [bct[0]["y"]])
    else:
        A["boardmark"].set_data([], [])
    rcts = [c for c in res["contacts"] if c["kind"] == "rim"]
    if rcts:
        A["rimmark"].set_offsets(np.array([(c["x"], c["y"]) for c in rcts]))
    else:
        A["rimmark"].set_offsets(np.empty((0, 2)))

    # status strip
    status = res["outcome"]
    if t is not None and t < res["T"][-1] - 1e-9:
        status = f"IN FLIGHT   t = {t:.2f} s"
    col = GOOD if res["made"] else (MUTED if status.startswith("IN FLIGHT") else BAD)
    A["status"].set_text(status); A["status"].set_color(col)
    head = (f"height {h0:.2f} m · angle {ang:.0f}{DEG} · spin {spin:.0f} rad/s · "
            f"speed {v:.2f} m/s · hoop {dist:.2f} m"
            + ("  · AIR OFF" if not res["air"] else ""))
    A["headtxt"].set_text(head)
    return status


def build_legend(ax, A, segs, slope_i, a2_i, h0, show_real, show_ideal, flying):
    """legend rebuilt only on refresh (not per animation frame)."""
    handles = []
    names = ["fitted arc, air + spin", "fitted arc, after board bounce",
             "fitted arc, reverse branch"]
    if show_real:
        for k, sg in enumerate(segs[:3]):
            A["fit"][k].set_label(
                f"{names[k]}  y = {sg['a2']:.4f}x² {sg['a1']:+.3f}x {sg['a0']:+.2f}")
            handles.append(A["fit"][k])
    if show_ideal:
        A["ideal"].set_label(
            f"ideal parabola (no air)  y = {h0:.2f} + {slope_i:.3f}x − {a2_i:.4f}x²")
        handles.append(A["ideal"])
    A["flight"].set_label("flight so far" if flying else "exact RK4 integration")
    handles.append(A["flight"])
    leg = ax.legend(handles=handles, loc="lower right", fontsize=8.5)
    fr = leg.get_frame()
    fr.set_facecolor(PANEL); fr.set_edgecolor(GRID); fr.set_alpha(0.95)
    for lt in leg.get_texts(): lt.set_color(INK)


def update_info(axp, params, res, window):
    h0, ang, spin, v, dist = params
    segs = fit_segments(res)
    ixs, iys, slope_i, a2_i, x_land = ideal_parabola(h0, ang, v)

    axp.set_facecolor(PANEL)
    axp.clear(); axp.set_xlim(0, 1); axp.set_ylim(0, 1); axp.axis("off")
    for sp in axp.spines.values(): sp.set_visible(False)

    def row(y, key, val, color=INK, size=9):
        axp.text(0.04, y, key, color=MUTED, fontsize=size - 0.5, va="center",
                 fontfamily="Consolas")
        axp.text(0.50, y, val, color=color, fontsize=size, va="center",
                 fontfamily="Consolas", fontweight="bold")

    axp.text(0.5, 0.978, "S H O T   R E A D - O U T", color=MUTED, fontsize=9,
             ha="center", va="top", fontfamily="Consolas")
    big = 18 if len(res["outcome"]) <= 12 else 12
    col = GOOD if res["made"] else BAD
    axp.text(0.5, 0.918, res["outcome"], color=col, fontsize=big, ha="center",
             va="center", fontweight="bold")
    axp.plot([0.04, 0.96], [0.868, 0.868], color=GRID, lw=1.0)

    # ---- collision / drag / spin aware trajectory function ----
    axp.text(0.04, 0.828, "TRAJECTORY FUNCTION  (arc, spin, air and board included)",
             color=TEAL, fontsize=9, va="center", fontfamily="Consolas",
             fontweight="bold")
    y = 0.784
    for i, sg in enumerate(segs[:3]):
        if len(segs) == 1:
            br = "y(x) = "
        elif not sg["after"]:
            br = "branch 1 (launch to first bounce): "
        else:
            br = f"branch {i + 1} (after a bounce): "
        rng = f"on {sg['x0']:.2f} ≤ x ≤ {sg['x1']:.2f}"
        eq = f"y = {sg['a2']:.4f}x² {sg['a1']:+.3f}x {sg['a0']:+.2f}"
        axp.text(0.04, y, eq, color=INK, fontsize=9.5, va="center",
                 fontfamily="Consolas")
        axp.text(0.04, y - 0.038, f"{br}{rng}", color=MUTED, fontsize=8,
                 va="center", fontfamily="Consolas")
        y -= 0.080
    board_ct = [c for c in res["contacts"] if c["kind"] == "board"]
    if board_ct:
        c = board_ct[0]
        axp.text(0.04, y, f"board hit at x {c['x']:.2f}, y {c['y']:.2f}: "
                 f"v in ({c['tin'][0]:.2f},{c['tin'][1]:.2f}) → out "
                 f"({c['tout'][0]:.2f},{c['tout'][1]:.2f})",
                 color="#FFD166", fontsize=8, va="center", fontfamily="Consolas")
        y -= 0.042
    axp.text(0.04, y,
             f"ideal no-air, same aim: y = {h0:.2f} + {slope_i:.3f}x − {a2_i:.4f}x²",
             color=VIOLET, fontsize=8.5, va="center", fontfamily="Consolas")
    y -= 0.042
    if len(segs) and abs(segs[0]["a2"]) > 1e-6:
        gain = (abs(a2_i) - abs(segs[0]["a2"])) / abs(a2_i) * 100
        axp.text(0.04, y,
                 f"curvature flatter than ideal by {gain:.0f}% from drag + Magnus lift",
                 color=MUTED, fontsize=8.5, va="center", fontfamily="Consolas")
    y -= 0.030
    axp.plot([0.04, 0.96], [y, y], color=GRID, lw=1.0)

    # ---- stat rows: spacing adapts to how many rows there are so nothing
    # ---- spills past the bottom of the panel or overlaps the footer
    rows = []
    rows.append(("hang time", f"{res['T'][-1]:.2f} s", INK))
    entry = f"{res['entry']:.1f}{DEG}" if res["entry"] is not None else "n/a"
    rows.append(("entry angle", entry, INK))
    rows.append(("apex height",
                 f"{res['peak']:.2f} m  ({res['peak'] - YR:+.2f} vs rim)", INK))
    if res["plane_h"] is not None:
        dcm = (YR - res["plane_h"]) * 100
        rows.append(("at hoop plane",
                     (f"{dcm:.0f} cm below the rim" if dcm > 2
                      else "level with the rim"),
                     BAD if dcm > 2 else GOOD))
    rows.append(("collisions", f"board {len(board_ct)}, rim {res['edge']}", INK))
    if res["air"]:
        ad = BD * v * v
        am = BM * abs(spin * math.sin(math.radians(ang))) * v
        rows.append(("launch drag",
                     f"{ad:.2f} m/s² ({ad / GRAV * 100:.0f}% of g)", INK))
        rows.append(("launch Magnus",
                     f"{am:.2f} m/s² ({am / GRAV * 100:.0f}% of g)", INK))
        ref = vacuum_aim(h0, ang, dist)
        if ref:
            cost = (v - ref[0]) / ref[0] * 100
            rows.append(("vacuum minimum", f"{ref[0]:.2f} m/s ({cost:+.1f}%)", INK))
    if window:
        lo, hi, mid, oc = window
        rows.append(("score window", f"{lo:.2f} to {hi:.2f} m/s", INK))
        rows.append(("window width", f"{hi - lo:.2f} m/s  ({oc})", ACCENT))
    else:
        rows.append(("score window", "press SCAN WINDOW", MUTED))

    y_row = y - 0.022
    step = min(0.044, max(0.030, (y_row - 0.045) / max(len(rows) - 1, 1)))
    for key, val, c in rows:
        row(y_row, key, val, color=c)
        y_row -= step
    y = y_row + step

    # footer captions only when there is room left, so they never overlap rows
    if y > 0.10:
        axp.plot([0.04, 0.96], [y - 0.006, y - 0.006], color=GRID, lw=1.0)
        axp.text(0.5, y - 0.034,
                 "fitted quadratics reproduce drag, spin and the bounce",
                 color=MUTED, fontsize=8, ha="center", va="center",
                 fontfamily="Consolas")
        axp.text(0.5, y - 0.060,
                 "in the coefficients - exact curve is the RK4 line",
                 color=MUTED, fontsize=8, ha="center", va="center",
                 fontfamily="Consolas")
    axp.figure.canvas.draw_idle()


# ============ interactive app ============

def main():
    params = [2.00, 45.0, 23.0, 8.41, FT_DIST]
    store = dict(res=None, window=None, anim=None, playing=False,
                 air=True, real=True, ideal=True, slow=False, loop=True)

    fig = plt.figure(figsize=(13.33, 7.5), facecolor=BG)
    fig.suptitle("Physics-Based Basketball Shot Simulator — COMP1110",
                 color=INK, fontsize=15, y=0.968, x=0.055, ha="left",
                 fontweight="bold")
    fig.text(0.055, 0.928,
             "the teal arc is a quadratic y(x) fitted to the full flight, so it "
             "carries backspin, air drag and the board bounce in its coefficients",
             color=MUTED, fontsize=10, ha="left")

    ax  = fig.add_axes([0.045, 0.335, 0.60, 0.56])
    axp = fig.add_axes([0.660, 0.335, 0.29, 0.56])

    A = init_scene(ax)

    def refresh():
        store["res"] = simulate(*params, air=store["air"])
        res = store["res"]
        update_scene(ax, A, params, res, None, store["real"], store["ideal"])
        segs = fit_segments(res)
        _, _, slope_i, a2_i, _ = ideal_parabola(params[0], params[1], params[3])
        build_legend(ax, A, segs, slope_i, a2_i, params[0],
                     store["real"], store["ideal"], False)
        update_info(axp, params, res, store["window"])

    # sliders: name (left) and live value (right) sit on their own line above
    # the track, so the number is never covered by the thumb or the track
    def sld(x, y, name, lo, hi, init, idx, valfmt="%.2f"):
        a = fig.add_axes([x, y, 0.27, 0.030]); a.set_facecolor(PANEL)
        s = Slider(a, "", lo, hi, valinit=init, valstep=0.01,
                   color=ACCENT, track_color=BTN)
        s.valtext.set_visible(False)
        fig.text(x, y + 0.036, name, color=MUTED, fontsize=9,
                 ha="left", va="bottom")
        val = fig.text(x + 0.27, y + 0.036, valfmt % init, color=INK, fontsize=9,
                       ha="right", va="bottom", fontfamily="Consolas",
                       fontweight="bold")
        def cb(_):
            params[idx] = float(s.val)
            val.set_text(valfmt % s.val)
            store["window"] = None
            refresh()
        s.on_changed(cb)
        return s

    sh = sld(0.045, 0.245, "release height (m)",  1.40, 2.60, 2.00, 0)
    sa = sld(0.045, 0.180, "release angle (deg)", 30.0, 70.0, 45.0, 1, valfmt="%.0f")
    ss = sld(0.045, 0.115, "backspin (rad/s)",     0.0, 40.0, 23.0, 2, valfmt="%.0f")
    sv = sld(0.345, 0.245, "launch speed (m/s)",   5.5, 14.5, 8.41, 3)
    sd = sld(0.345, 0.180, "rim distance (m)",     4.20, 7.20, FT_DIST, 4)

    def mk_btn(x, y, w, h, label, hover=NAVY, fg=INK, size=9.5, bold=False):
        a = fig.add_axes([x, y, w, h]); a.set_facecolor(BTN)
        b = Button(a, label, hovercolor=hover, color=BTN)
        b.label.set_color(fg); b.label.set_fontsize(size)
        if bold: b.label.set_fontweight("bold")
        return b

    def mk_tgl(x, y, w, h, on_txt, off_txt, init, oncolor, action):
        a = fig.add_axes([x, y, w, h])
        base = oncolor if init else BTN
        a.set_facecolor(base)
        b = Button(a, on_txt if init else off_txt, hovercolor="#42516A", color=base)
        b.label.set_color(INK if init else MUTED); b.label.set_fontsize(8.5)
        st = {"on": init}
        def apply(val):
            st["on"] = val
            c = oncolor if val else BTN
            b.color = c
            a.set_facecolor(c)
            b.label.set_text(on_txt if val else off_txt)
            b.label.set_color(INK if val else MUTED)
            action(val)
        def flip(_): apply(not st["on"])
        b.on_clicked(flip)
        b.set_state = apply
        return b

    b_shoot = mk_btn(0.660, 0.245, 0.13, 0.055, "SHOOT", hover="#2B7BCF",
                     size=12, bold=True)
    b_scan  = mk_btn(0.802, 0.245, 0.148, 0.055, "SCAN WINDOW", hover="#7A4CBF")
    b_ft    = mk_btn(0.660, 0.180, 0.13, 0.05, "FREE THROW")
    b_pk    = mk_btn(0.802, 0.180, 0.148, 0.05, "PEAK CELL 51°/23")
    b_3p    = mk_btn(0.660, 0.115, 0.13, 0.05, "THREE POINT")
    b_tl    = mk_btn(0.802, 0.115, 0.07, 0.05, "2.30 m")
    b_sm    = mk_btn(0.880, 0.115, 0.07, 0.05, "1.60 m")

    def on_real(val):  store["real"] = val;  refresh()
    def on_ideal(val): store["ideal"] = val; refresh()
    def on_air(val):   store["air"] = val;   refresh()
    def on_slow(val):  store["slow"] = val
    def on_loop(val):  store["loop"] = val

    t_real = mk_tgl(0.345, 0.115, 0.135, 0.05, "REAL ARC ON", "REAL ARC OFF",
                    True, TEAL, on_real)
    t_ideal = mk_tgl(0.492, 0.115, 0.135, 0.05, "IDEAL ARC ON", "IDEAL ARC OFF",
                     True, VIOLET, on_ideal)
    t_air = mk_tgl(0.345, 0.050, 0.11, 0.05, "AIR ON", "AIR OFF",
                   True, "#4FA8E0", on_air)
    t_slow = mk_tgl(0.468, 0.050, 0.13, 0.05, "SLOW-MO ON", "REAL TIME",
                    False, "#4CBF9A", on_slow)
    t_loop = mk_tgl(0.612, 0.050, 0.12, 0.05, "LOOP ON", "LOOP OFF",
                    True, "#C7A40A", on_loop)

    def set_all(h, a, sp, vv, dd):
        params[0] = h; params[1] = a; params[2] = sp; params[3] = vv; params[4] = dd
        store["window"] = None
        sh.set_val(h); sa.set_val(a); ss.set_val(sp); sv.set_val(vv); sd.set_val(dd)

    def on_ft(_):    set_all(2.00, 51.0, 23.0, 7.90, FT_DIST)
    def on_3p(_):    set_all(2.00, 45.0, 23.0, 9.46, PT_DIST)
    def on_pk(_):    set_all(2.00, 51.0, 23.0, 7.90, FT_DIST)
    def on_tl(_):    set_all(2.30, 51.0, 23.0, 7.50, FT_DIST)
    def on_sm(_):    set_all(1.60, 51.0, 23.0, 8.65, FT_DIST)
    b_ft.on_clicked(on_ft); b_3p.on_clicked(on_3p); b_pk.on_clicked(on_pk)
    b_tl.on_clicked(on_tl); b_sm.on_clicked(on_sm)

    def on_scan(_=None):
        out = find_band(params[0], params[1], params[2], params[4],
                        want="made", air=store["air"])
        store["window"] = out
        if out:
            lo, hi, mid, oc = out
            params[3] = mid
            sv.set_val(mid)
            ax.set_title(f"scoring speeds {lo:.2f} to {hi:.2f} m/s "
                         f"(width {hi - lo:.2f}); set to midpoint {mid:.2f} "
                         f"m/s → {oc}", color=INK, fontsize=10, pad=6)
        else:
            ax.set_title(f"no launch speed in 5.5-14.5 m/s scores at "
                         f"{params[1]:.0f}{DEG}, {params[2]:.0f} rad/s, "
                         f"{params[0]:.2f} m", color=BAD, fontsize=10, pad=6)
        refresh()
    b_scan.on_clicked(on_scan)

    def on_shoot(_=None):
        if store["playing"]: return
        res = store["res"]; T = res["T"]
        if T[-1] < 0.02: return
        store["playing"] = True
        step_t = 0.04
        frames = list(np.arange(0.0, max(T[-1] - step_t, 0.0), step_t))
        frames.append(float(T[-1]))
        def frame(tt):
            # artists only mutate here; the read-out panel is static during
            # flight so it is not redrawn (no flicker, no numeric overlap)
            update_scene(ax, A, params, res, float(tt), store["real"], store["ideal"])
            if abs(float(tt) - T[-1]) < 1e-9:
                store["playing"] = False
                if store["loop"]:
                    on_shoot()
        interval = 40 / (0.35 if store["slow"] else 1.0)
        store["anim"] = FuncAnimation(fig, frame, frames=frames,
                                      interval=interval, blit=False)
    b_shoot.on_clicked(on_shoot)

    refresh()
    plt.show()


def headless_check():
    """无头自检: 复算 6 个 DEMO_SCENES 并与原版逐位对照 (供 CI, 不开窗口)。"""
    import basketball_shot_2d as _orig
    ok = 0
    for name, h0, ang, spin, v, dist, air, expect in DEMO_SCENES:
        a = _orig.simulate(h0, ang, spin, v, dist, air=air)
        b = simulate(h0, ang, spin, v, dist, air=air)
        same_arrays = all(np.array_equal(a[k], b[k]) for k in ("T", "X", "Y"))
        same_meta = (a["outcome"] == b["outcome"] == expect
                     and a["made"] == b["made"]
                     and a["plane_h"] == b["plane_h"] and a["peak"] == b["peak"]
                     and len(a["contacts"]) == len(b["contacts"]))
        ok += 1 if (same_arrays and same_meta) else 0
        print(f"  {'OK ' if same_arrays and same_meta else 'DIVERGE'} {name}: {b['outcome']}")
    # 输入加固 (原版在这两个输入上会 ZeroDivisionError / 退化)
    try:
        ideal_parabola(2.0, 51.0, 0.0)
        print("  [XX] ideal_parabola(v=0) 未拒绝")
    except ValueError:
        print("  OK  ideal_parabola(v=0) 干净拒绝 (原版 ZeroDivisionError)")
    ref_old = _orig.vacuum_aim(2.0, 90.0, 4.6)
    ref_new = vacuum_aim(2.0, 90.0, 4.6)
    print(f"  NOTE vacuum_aim(90°): 原版返回退化值 v={ref_old[0]:.3e} m/s (垂直仰角打不出"
          f"水平射程), 改进版按不可达返回 None — 仅这个机器精度的极端输入不同")
    print(f"\nbasketball_shot_2d_improved --check: 场景逐位一致 {ok}/{len(DEMO_SCENES)}")
    return ok == len(DEMO_SCENES)


if __name__ == "__main__":
    if "--check" in sys.argv[1:]:
        sys.exit(0 if headless_check() else 1)
    main()
