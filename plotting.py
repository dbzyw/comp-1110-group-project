"""
plotting.py — 命中概率热力图与轨迹对比可视化

提供五类图 (命中概率热力图 / 罚球vs三分对比 / 结局分解 /
真空vs真实轨迹对比 / 阻力偏差对比)，并包含以下修正与校验:

    * 修复显示 bug: plot_free_vs_three 原先把出手点到筐心的水平距离算成
      X0 - rim_x = -4.195 / THREE_X0 - rim_x = -6.75，图例与柱标签印出
      "-4.19 m" / "-6.75 m" (负距离)。改进版取绝对值, 与其余图注一致
      (这是模型图注的有意修正)
    * _read_sweep: 校验 p_make 值全部有限且落在 [0, 1]、网格行序与
      angle × backspin 展开一致 (CSV 被手工编辑出错时给出明确报错,
      而不是悄悄画出错位热力图)
    * vacuum_launch_angle / vacuum_trajectory / interp_y_at_x:
      v <= 0、cos(θ) ≈ 0 (垂直发射)、x_target 在轨迹范围外时显式报错,
      而不是 ZeroDivisionError / 静默 clip 外推
    * 新增 `python plotting.py selfcheck`: 把全部图重画到临时
      目录做烟雾测试 (不改变默认命令行行为)

用法:
    python plotting.py                 # 画全部图
    python plotting.py breakdown       # 只画结局分解图
    python plotting.py selfcheck       # 全部图重画到临时目录自检
"""

from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")                       # 无 GUI 环境直接保存图片
import matplotlib.pyplot as plt

from data_validation.data_prep import DEFAULT_BACKSPIN_RAD_S
from physics import G, release_velocity, integrate
from collision import RIM_HEIGHT, RIM_CENTER, BACKBOARD_X, RIM_TO_BOARD

DATA_CSV = "data.csv"
REQUIRED_COLUMNS = ("angle", "backspin", "p_make")


# ===========================================================================
# 1) 命中概率热力图 (Make-Probability Surface)
# ===========================================================================
def _read_sweep(csv_path=DATA_CSV):
    """读取并校验 data.csv, 返回 (angles, backspins, data 结构化数组)。"""
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"找不到 {csv_path}。请先运行 `python experiment.py` 生成它。")

    try:
        data = np.genfromtxt(path, delimiter=",", names=True, dtype=float)
    except (OSError, ValueError) as e:
        raise ValueError(f"读取 {csv_path} 失败 (不是合法的 CSV?): {e}") from e

    cols = data.dtype.names or ()
    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    if missing:
        raise ValueError(f"{csv_path} 缺少列 {missing}, 期望列 {list(REQUIRED_COLUMNS)}")

    angles = np.unique(data["angle"])
    backspins = np.unique(data["backspin"])
    expected = len(angles) * len(backspins)
    if data.size != expected:
        raise ValueError(
            f"{csv_path} 网格不完整: 期望 {expected} 行 "
            f"({len(angles)} 角度 × {len(backspins)} 后旋), 实际 {data.size} 行")

    # 改进版新增的两道校验 (experiment.py 生成的文件天然满足)
    p = data["p_make"]
    if not np.all(np.isfinite(p)) or np.any(p < 0.0) or np.any(p > 1.0):
        raise ValueError(
            f"{csv_path} 的 p_make 列必须全部落在 [0, 1] 且有限 "
            f"(min={np.nanmin(p)}, max={np.nanmax(p)}) — CSV 可能被手工改坏")
    grid_ok = (data["angle"].reshape(len(angles), len(backspins))
               == angles[:, None]).all() and \
              (data["backspin"].reshape(len(angles), len(backspins))
               == backspins[None, :]).all()
    if not grid_ok:
        raise ValueError(
            f"{csv_path} 行序与 '每个角度 × 每个后旋' 的展开顺序不一致 "
            f"(应为角度外层、后旋内层; 用 experiment.py 重新生成)")
    return angles, backspins, data


def load_sweep(csv_path=DATA_CSV):
    """读取 data.csv, 返回 (angles, backspins, P)。"""
    angles, backspins, data = _read_sweep(csv_path)
    P = data["p_make"].reshape(len(angles), len(backspins))
    return angles, backspins, P


def load_sweep_full(csv_path=DATA_CSV):
    """读取 data.csv 的完整列 (含 swish/rim-in/board-in 分解)。

    返回 (angles, backspins, P, P_swish, P_rim, P_board);
    若 CSV 缺少分解列, 对应项返回 None。
    """
    angles, backspins, data = _read_sweep(csv_path)
    cols = data.dtype.names or ()
    shape = (len(angles), len(backspins))
    P = data["p_make"].reshape(shape)
    P_swish = data["p_swish"].reshape(shape) if "p_swish" in cols else None
    P_rim = data["p_rim_in"].reshape(shape) if "p_rim_in" in cols else None
    P_board = data["p_board_in"].reshape(shape) if "p_board_in" in cols else None
    return angles, backspins, P, P_swish, P_rim, P_board


def _draw_sweep(ax, angles, backspins, P, title, vmax=None, draw_50=True):
    """在给定 axes 上画一张命中概率热力图, 返回 (colorable, (peak_ang, peak_back, peak_p))。

    vmax   : 色标上限 (默认 1.0); 分解图的 swish/rim/board 概率小, 传各自最大值自动缩放
    draw_50: 是否画 50% 等值线 (仅对总命中率有意义, 分解图通常关闭)
    """
    X, Y = np.meshgrid(backspins, angles)        # X=后旋, Y=角度
    vmax = 1.0 if vmax is None else max(float(vmax), 1e-6)
    cf = ax.contourf(X, Y, P, levels=np.linspace(0.0, vmax, 21),
                     cmap="viridis", extend="both")

    if draw_50:
        cs = ax.contour(X, Y, P, levels=[0.5], colors="white",
                        linewidths=2.0, linestyles="--")
        ax.clabel(cs, fmt={0.5: "50%"}, inline=True, fontsize=9, colors="white")

    # 峰值星星
    i, j = np.unravel_index(np.argmax(P), P.shape)
    peak = (angles[i], backspins[j], P[i, j])
    ax.scatter([backspins[j]], [angles[i]], marker="*", s=420, color="gold",
               edgecolors="black", linewidths=1.2, zorder=5,
               label=f"peak {P[i, j]:.2f} @ {angles[i]:.1f}°, {backspins[j]:.1f} rad/s")

    ax.set_xlabel("backspin rate (rad/s)")
    ax.set_ylabel("release angle (deg)")
    ax.set_title(title)
    ax.legend(loc="lower right", fontsize=8)
    return cf, peak


def plot_make_probability(csv_path=DATA_CSV, out_png="make_probability.png", dpi=300):
    """命中概率热力图: 横轴后旋速率, 纵轴出手角度; 标 50% 等值线与峰值星星。"""
    angles, backspins, P = load_sweep(csv_path)
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    cf, (peak_ang, peak_back, peak_p) = _draw_sweep(
        ax, angles, backspins, P, "Make-probability surface  (dashed = 50%)")
    fig.colorbar(cf, ax=ax, label="P(make)")
    fig.tight_layout()
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"已保存 {out_png}  (峰值 P={peak_p:.3f} @ {peak_ang:.1f}°, {peak_back:.1f} rad/s)")
    return out_png


def plot_make_probability_comparison(free_csv=DATA_CSV, three_csv="data_three.csv",
                                     out_png="make_probability_comparison.png", dpi=300):
    """罚球 vs 三分球 命中概率热力图并排对比 (共享色标, 各自标峰值)。"""
    fa, fb, fP = load_sweep(free_csv)
    ta, tb, tP = load_sweep(three_csv)

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(13.0, 5.4))
    _draw_sweep(ax0, fa, fb, fP, "Free throw (4.57 m)")
    cf1, (a1, b1, p1) = _draw_sweep(ax1, ta, tb, tP, "Three-pointer (6.75 m)")

    # 共享色标
    fig.colorbar(cf1, ax=[ax0, ax1], label="P(make)")

    fig.suptitle("Make-probability surface: free throw vs three-pointer", fontsize=13)
    fig.subplots_adjust(wspace=0.25, top=0.88, bottom=0.12)
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    i0, j0 = np.unravel_index(np.argmax(fP), fP.shape)
    a0, b0, p0 = fa[i0], fb[j0], fP[i0, j0]
    print(f"已保存 {out_png}")
    print(f"  罚球  峰值 P={p0:.3f} @ {a0:.1f}°, {b0:.1f} rad/s")
    print(f"  三分  峰值 P={p1:.3f} @ {a1:.1f}°, {b1:.1f} rad/s")
    print(f"  峰值角度变化 {a0:.1f}° -> {a1:.1f}° (Δ{a1 - a0:+.1f}°), "
          f"后旋 {b0:.1f} -> {b1:.1f} rad/s (Δ{b1 - b0:+.1f})")
    return out_png, (a0, b0, p0, a1, b1, p1)


def plot_outcome_breakdown(csv_path=DATA_CSV, out_png="outcome_breakdown.png", dpi=300):
    """把命中概率拆成 swish / rim-in / board-in 三张分图, 与总命中率拼成 2×2。

    每个子图用各自的最大值做色标 (swish 占大头, rim/board 概率小, 自动缩放才看得清);
    总命中率面板仍保留 50% 等值线。
    """
    angles, backspins, P, P_swish, P_rim, P_board = load_sweep_full(csv_path)
    if P_swish is None or P_rim is None or P_board is None:
        print(f"跳过 {out_png}: {csv_path} 缺少分解列 "
              f"(p_swish/p_rim_in/p_board_in), 请用最新版 experiment.py 重新生成")
        return None

    fig, axes = plt.subplots(2, 2, figsize=(12.5, 9.5))
    panels = [
        (axes[0, 0], P,       "P(make)",     True),
        (axes[0, 1], P_swish, "P(swish)",    False),
        (axes[1, 0], P_rim,   "P(rim-in)",   False),
        (axes[1, 1], P_board, "P(board-in)", False),
    ]
    for ax, grid, title, draw_50 in panels:
        vmax = 1.0 if draw_50 else grid.max()
        cf, _ = _draw_sweep(ax, angles, backspins, grid, title,
                            vmax=vmax, draw_50=draw_50)
        fig.colorbar(cf, ax=ax, label="probability")

    fig.suptitle("Outcome breakdown: swish vs rim-in vs board-in", fontsize=14)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    print(f"已保存 {out_png}")
    return out_png


# ===========================================================================
# 2) 真空瞄准 vs 真实飞行 轨迹对比
# ===========================================================================
# 出手条件 (真空 vs 真实轨迹对比)
X0, Y0 = -4.57, 2.0          # 出手点 (距篮板 4.57 m, 高 2.0 m)
V0 = 7.3                      # 出手速率 [m/s]; 选 7.3 使真空瞄准仰角≈55°, 接近自然罚球弧线
BACKSPIN = DEFAULT_BACKSPIN_RAD_S  # 后旋 [rad/s]

# 三分球出手条件 (FIBA 三分线距筐心 6.75 m)
THREE_DIST = 6.75                        # 三分线到筐心水平距离 [m]
THREE_X0 = -(THREE_DIST + RIM_TO_BOARD)  # 出手点 x = -7.125 m (距篮板 7.125 m)
THREE_Y0 = 2.0                           # 出手高度 [m], 与罚球一致以隔离距离影响
THREE_V0 = 8.9                           # 出手速率 [m/s]; 使真空瞄准仰角≈55°, 与罚球接近
THREE_BACKSPIN = DEFAULT_BACKSPIN_RAD_S  # 后旋 [rad/s], 与罚球一致


def vacuum_launch_angle(x0, y0, x1, y1, v):
    """
    重力-only 抛体从 (x0, y0) 以速率 v 命中 (x1, y1) 所需仰角 [deg]。
    返回高弧线解 (角度较大的那个)。
    改进版: v <= 0 或 x1 == x0 (同一竖直线) 显式报错, 而不是 ZeroDivisionError/NaN。
    """
    v = float(v)
    if v <= 0.0:
        raise ValueError(f"v must be positive, got {v!r}")
    dx = x1 - x0
    dy = y1 - y0
    a = 0.5 * G * dx ** 2 / v ** 2
    if a == 0.0:
        raise ValueError(
            f"x1 == x0 (dx = {dx!r}): 目标点与出手点在同一竖直线上, 无真空抛物线解")
    b = -dx
    c = dy + a
    disc = b ** 2 - 4.0 * a * c
    if disc < 0.0:
        raise ValueError("目标点不可达 (出手速率太小)")
    u = (-b + np.sqrt(disc)) / (2.0 * a)       # 高弧线: tan(θ) 较大根
    return np.degrees(np.arctan(u))


def vacuum_trajectory(x0, y0, v, angle_deg, x_end, n=300):
    """真空(仅重力)解析轨迹, 从 x0 到 x_end。"""
    n = int(n)
    if n < 2:
        raise ValueError(f"n must be >= 2, got {n!r}")
    v = float(v)
    if v <= 0.0:
        raise ValueError(f"v must be positive, got {v!r}")
    th = np.radians(angle_deg)
    vx, vy = v * np.cos(th), v * np.sin(th)
    if abs(vx) < 1e-12:
        raise ValueError(
            f"angle_deg={angle_deg!r} is vertical; no x-monotone vacuum arc")
    t_end = (x_end - x0) / vx
    t = np.linspace(0.0, t_end, n)
    x = x0 + vx * t
    y = y0 + vy * t - 0.5 * G * t ** 2
    return x, y


def interp_y_at_x(xs, ys, x_target):
    """
    在轨迹上线性插值, 求 x = x_target 处的 y。

    改进版: x_target 落在轨迹范围外时显式报错 (原版用 clip 静默外推端点值,
    在“球根本没到筐面”的情形下会把偏差画成 ~0)。
    """
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    if xs.shape != ys.shape or xs.ndim != 1 or xs.size < 2:
        raise ValueError("xs/ys must be matching 1-D arrays with at least 2 points")
    x_target = float(x_target)
    if not (xs[0] <= x_target <= xs[-1]):
        raise ValueError(
            f"x_target={x_target:.3f} outside trajectory x-range "
            f"[{xs[0]:.3f}, {xs[-1]:.3f}] — the shot never reached that plane")
    i = int(np.clip(np.searchsorted(xs, x_target), 1, len(xs) - 1))
    x0, x1 = xs[i - 1], xs[i]
    y0, y1 = ys[i - 1], ys[i]
    frac = (x_target - x0) / (x1 - x0) if x1 != x0 else 0.0
    return y0 + frac * (y1 - y0)


def simulate_shot_pair(x0, y0, v0, backspin, rim_x=RIM_CENTER[0], rim_y=RIM_HEIGHT):
    """
    计算一次投篮的“真空瞄准”与“真实飞行”两条轨迹。

    真空轨迹用解析式 (仅重力, 精确命中筐心); 真实轨迹用 RK4 积分
    (重力 + 二次阻力 + 马格努斯升力), 积分到筐面 (x = rim_x) 为止。

    返回
    ----
    ang_vac       : float  真空瞄准仰角 [deg]
    x_vac, y_vac  : 真空轨迹 (x, y)
    x_real, y_real: 真实轨迹 (x, y)
    y_at_rim      : float  真实轨迹到达筐面时的 y [m]
    deviation_cm  : float  相对筐心的竖直偏差 [cm] (正 = 偏低/短)
    """
    ang_vac = vacuum_launch_angle(x0, y0, rim_x, rim_y, v0)
    x_vac, y_vac = vacuum_trajectory(x0, y0, v0, ang_vac, rim_x + 0.4)

    v0_vec = release_velocity(v0, ang_vac)
    _, states = integrate([x0, y0, 0.0], v0_vec, backspin,
                          stop=lambda s: s[0] >= rim_x)
    x_real, y_real = states[:, 0], states[:, 1]

    y_at_rim = interp_y_at_x(x_real, y_real, rim_x)
    deviation_cm = (rim_y - y_at_rim) * 100.0
    return ang_vac, x_vac, y_vac, x_real, y_real, y_at_rim, deviation_cm


def plot_trajectory_comparison(out_png="trajectory_comparison.png", dpi=300):
    """两条轨迹: 真空瞄准(命中筐心) vs 真实(阻力+后旋, 偏低), 并标注偏差。"""
    rim_x, rim_y = RIM_CENTER[0], RIM_HEIGHT      # NBA opening centre / top plane (-0.381, 3.048)

    ang_vac, x_vac, y_vac, x_real, y_real, y_at_rim, deviation_cm = \
        simulate_shot_pair(X0, Y0, V0, BACKSPIN, rim_x, rim_y)
    print(f"      真空瞄准仰角 = {ang_vac:.2f}°")
    print(f"      到达筐面: 真空 y = {rim_y:.3f} m, 真实 y = {y_at_rim:.3f} m, "
          f"偏低 {deviation_cm:.1f} cm")

    fig, ax = plt.subplots(figsize=(8.5, 5.2))

    ax.plot(x_vac, y_vac, "-", color="#1f77b4", lw=2.2,
            label="no air drag (vacuum aim)")
    ax.plot(x_real, y_real, "--", color="#d62728", lw=2.2,
            label="with drag + backspin")
    ax.plot(rim_x, rim_y, "o", color="black", ms=9, label="rim center")
    ax.axvline(BACKBOARD_X, color="gray", ls=":", lw=1.5, label="backboard")

    # 偏差标注
    ax.annotate(f"{deviation_cm:.1f} cm low",
                xy=(rim_x, y_at_rim), xytext=(rim_x - 1.6, y_at_rim - 0.35),
                arrowprops=dict(arrowstyle="->", color="black", lw=1.2),
                fontsize=11)

    ax.set_xlabel("x (m)   [shooter → hoop]")
    ax.set_ylabel("y (m)")
    ax.set_title("Vacuum aim vs. real flight (drag + Magnus)")
    ax.legend(loc="lower right")
    ax.set_ylim(0.0, 4.4)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    print(f"已保存 {out_png}  (偏低 {deviation_cm:.1f} cm)")
    return out_png, deviation_cm


def plot_trajectory_comparison_three(out_png="trajectory_comparison_three.png", dpi=300):
    """三分球: 真空瞄准 vs 真实飞行 轨迹对比 (FIBA 6.75 m)。"""
    rim_x, rim_y = RIM_CENTER[0], RIM_HEIGHT

    ang_vac, x_vac, y_vac, x_real, y_real, y_at_rim, deviation_cm = \
        simulate_shot_pair(THREE_X0, THREE_Y0, THREE_V0, THREE_BACKSPIN, rim_x, rim_y)
    print(f"      三分球真空瞄准仰角 = {ang_vac:.2f}°  "
          f"(出手点 x = {THREE_X0:.3f} m, 距筐心 {THREE_DIST:.2f} m)")
    print(f"      到达筐面: 真空 y = {rim_y:.3f} m, 真实 y = {y_at_rim:.3f} m, "
          f"偏低 {deviation_cm:.1f} cm")

    fig, ax = plt.subplots(figsize=(8.5, 5.2))

    ax.plot(x_vac, y_vac, "-", color="#1f77b4", lw=2.2,
            label="no air drag (vacuum aim)")
    ax.plot(x_real, y_real, "--", color="#d62728", lw=2.2,
            label="with drag + backspin")
    ax.plot(rim_x, rim_y, "o", color="black", ms=9, label="rim center")
    ax.axvline(BACKBOARD_X, color="gray", ls=":", lw=1.5, label="backboard")

    ax.annotate(f"{deviation_cm:.1f} cm low",
                xy=(rim_x, y_at_rim), xytext=(rim_x - 2.8, y_at_rim - 0.55),
                arrowprops=dict(arrowstyle="->", color="black", lw=1.2),
                fontsize=11)

    ax.set_xlabel("x (m)   [shooter → hoop]")
    ax.set_ylabel("y (m)")
    ax.set_title("Three-pointer (6.75 m): vacuum aim vs. real flight (drag + Magnus)")
    ax.legend(loc="lower right")
    ax.set_ylim(0.0, 5.4)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    print(f"已保存 {out_png}  (偏低 {deviation_cm:.1f} cm)")
    return out_png, deviation_cm


def plot_free_vs_three(out_png="free_vs_three_drag.png", dpi=300):
    """罚球 vs 三分球: 空气阻力造成的下落偏差对比 (轨迹 + 柱状图)。"""
    rim_x, rim_y = RIM_CENTER[0], RIM_HEIGHT

    ft = simulate_shot_pair(X0, Y0, V0, BACKSPIN, rim_x, rim_y)
    tp = simulate_shot_pair(THREE_X0, THREE_Y0, THREE_V0, THREE_BACKSPIN, rim_x, rim_y)
    _, xv_ft, yv_ft, xr_ft, yr_ft, yrim_ft, dev_ft = ft
    _, xv_tp, yv_tp, xr_tp, yr_tp, yrim_tp, dev_tp = tp

    # 出手点到筐心的水平距离。bug 修复: 原版直接写 X0 - rim_x / THREE_X0 -
    # rim_x, 得到 -4.195 / -6.75, 图例和柱标签印成 "-4.19 m" / "-6.75 m";
    # 距离应当是非负的, 这里取绝对值 (与 docstring 和其余图注保持一致)。
    ft_dist = abs(X0 - rim_x)                # 罚球出手点到筐心水平距离 ≈ 4.19 m
    tp_dist = abs(THREE_X0 - rim_x)          # 三分出手点到筐心水平距离 = 6.75 m

    fig, (ax0, ax1) = plt.subplots(
        1, 2, figsize=(12.0, 5.0),
        gridspec_kw={"width_ratios": [1.7, 1.0]},
    )
    fig.suptitle("Air resistance: free throw vs three-pointer", fontsize=13)

    # ---- 左: 两条投篮的真空 vs 真实轨迹 (同一坐标系) ----
    ax0.plot(xv_ft, yv_ft, "-", color="#1f77b4", lw=2.0,
             label=f"free throw {ft_dist:.2f} m — vacuum")
    ax0.plot(xr_ft, yr_ft, "--", color="#d62728", lw=2.0,
             label=f"free throw — drag (−{dev_ft:.0f} cm)")
    ax0.plot(xv_tp, yv_tp, "-", color="#2ca02c", lw=2.0,
             label=f"three {tp_dist:.2f} m — vacuum")
    ax0.plot(xr_tp, yr_tp, "--", color="#ff7f0e", lw=2.0,
             label=f"three — drag (−{dev_tp:.0f} cm)")

    ax0.plot(rim_x, rim_y, "o", color="black", ms=8, zorder=6, label="rim center")
    ax0.axvline(BACKBOARD_X, color="gray", ls=":", lw=1.5, label="backboard")
    ax0.axhline(rim_y, color="gray", ls=":", lw=0.8, alpha=0.5)

    ax0.set_xlabel("x (m)   [shooter → hoop]")
    ax0.set_ylabel("y (m)")
    ax0.set_title("Trajectories (vacuum aim vs. real flight)")
    ax0.legend(loc="upper right", fontsize=8)
    ax0.set_xlim(THREE_X0 - 0.5, 0.4)
    ax0.set_ylim(0.0, 5.4)
    ax0.grid(True, alpha=0.3)

    # ---- 右: 空气阻力造成的筐面下落偏差柱状图 ----
    labels = [f"free throw\n({ft_dist:.2f} m)",
              f"three-pointer\n({tp_dist:.2f} m)"]
    values = [dev_ft, dev_tp]
    colors = ["#1f77b4", "#2ca02c"]
    bars = ax1.bar(labels, values, color=colors, width=0.55)
    for b, v in zip(bars, values):
        ax1.text(b.get_x() + b.get_width() / 2.0, v + 2.0, f"{v:.0f} cm",
                 ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax1.set_ylabel("drop below rim center (cm)")
    ax1.set_title("Drag-induced drop at rim")
    ax1.set_ylim(0.0, max(values) * 1.18)
    ax1.grid(axis="y", alpha=0.3)

    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    print(f"已保存 {out_png}  (罚球偏低 {dev_ft:.1f} cm, 三分偏低 {dev_tp:.1f} cm, "
          f"差异 {dev_tp - dev_ft:.1f} cm)")
    return out_png, (dev_ft, dev_tp)


# ---------------------------------------------------------------------------
# 全套图重画到指定目录 (原版也直接提供这个可组合入口)
# ---------------------------------------------------------------------------
def plot_all(out_dir=".", dpi=300):
    """按原版 __main__ 的顺序画全部 7 张图, 输出到 out_dir 下。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True) if str(out_dir) not in ("", ".") else None
    name = lambda f: str(out_dir / f) if str(out_dir) not in ("", ".") else f

    plot_make_probability(DATA_CSV, name("make_probability.png"), dpi)
    print()
    plot_make_probability("data_three.csv", name("make_probability_three.png"), dpi)
    print()
    plot_make_probability_comparison(DATA_CSV, "data_three.csv",
                                     name("make_probability_comparison.png"), dpi)
    print()
    plot_outcome_breakdown(DATA_CSV, name("outcome_breakdown.png"), dpi)
    print()
    plot_trajectory_comparison(name("trajectory_comparison.png"), dpi)
    print()
    plot_trajectory_comparison_three(name("trajectory_comparison_three.png"), dpi)
    print()
    plot_free_vs_three(name("free_vs_three_drag.png"), dpi)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    if mode == "breakdown":
        # 只画结局分解图 (swish / rim-in / board-in)
        plot_outcome_breakdown()
    elif mode == "selfcheck":
        # 烟雾自检: 全部图重画到临时目录, 校验文件确实产出 (不污染仓库)
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            plot_all(td)
            outs = sorted(Path(td).glob("*.png"))
            sizes = [(p.name, p.stat().st_size) for p in outs]
            bad = [n for n, sz in sizes if sz < 10_000]
            print(f"\nselfcheck: {len(sizes)}/7 张图产出"
                  + (f" , 异常偏小: {bad}" if bad else " , 全部大小正常"))
            for n, sz in sizes:
                print(f"  {n:<38} {sz / 1024:7.1f} KiB")
            sys.exit(0 if len(sizes) == 7 and not bad else 1)
    else:
        # 默认: 与 plotting.py 的 __main__ 完全相同的动作与输出文件名
        plot_all(".")
