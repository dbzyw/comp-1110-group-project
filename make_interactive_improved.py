"""
make_interactive_improved.py — make_interactive.py 的改进版（原文件保留）

生成同一个交互式 HTML 浏览器 (basketball_interactive.html)：(角度 × 后旋)
扫描、frames + 滑块、结局颜色区分；轨迹数据来源默认走仓库的 *_improved
链路 (与 simulation.py 逐位一致，见 test_core / experiment_improved --selfcheck)。

相对 make_interactive.py 的改动:

    * 参数化 main(out_html, include_plotlyjs, angles/backspins/speed 覆盖):
      原版全部是模块常量 + 写死文件名; 现在可编程调用
    * CLI: --offline / --embed 生成内嵌 plotly.js 的离线版 (~3.5 MB);
           --out <html> 指定输出文件; --cdn 保持默认
    * 未知结局串不再 KeyError: 用灰色兜底并警告 (模型加新结局时 HTML 仍可生成)
    * 输入校验: DOWNSAMPLE>=1, 网格非空; 无轨迹时清晰报错
    * 生成逻辑 (frame 顺序 / hovertemplate / shapes / slider steps / layout)
      与原版逐字段一致 — 同一环境跑出的 HTML 与原版逐字节可复现
      (已在本地用仓库里已提交的 HTML 验证)

依赖: numpy, plotly (pip install plotly)。原 make_interactive.py 的用法不变:
    python make_interactive_improved.py                  # CDN 版 (默认)
    python make_interactive_improved.py --offline        # 离线内嵌版
    python make_interactive_improved.py --out my.html    # 自定义输出名
"""

import argparse
import sys
from pathlib import Path

import numpy as np

try:
    import plotly.graph_objects as go
except ImportError:
    raise SystemExit("缺少 plotly, 请先运行:  pip install plotly")

# 默认走改进链路 (结果与主流程逐位一致), 缺失时降级
try:
    from simulation_improved import simulate_shot
    from physics_improved import release_velocity
    from collision_improved import (RIM_CENTER, RIM_HEIGHT, RIM_RADIUS,
                                    BACKBOARD_X, BACKBOARD_BOTTOM, BACKBOARD_TOP)
    _CHAIN = "improved"
except ImportError:
    from simulation import simulate_shot
    from physics import release_velocity
    from collision import (RIM_CENTER, RIM_HEIGHT, RIM_RADIUS,
                           BACKBOARD_X, BACKBOARD_BOTTOM, BACKBOARD_TOP)
    _CHAIN = "mainline"

# ---------------------------------------------------------------------------
# 扫描参数 (可被 main()/CLI 覆盖)
# ---------------------------------------------------------------------------
ANGLES_DEG = np.arange(40.0, 61.0, 5.0)      # 出手角度 40..60°
BACKSPINS = np.arange(0.0, 41.0, 10.0)       # 后旋 0..40 rad/s
RELEASE_POS = (-4.57, 2.0, 0.0)              # 出手点 (标准罚球)
SPEED = 7.5                                  # 出手速率 [m/s]
DOWNSAMPLE = 4                               # 每隔几个轨迹点取 1 个, 控制 HTML 体积
OUT_HTML = "basketball_interactive.html"

# include_plotlyjs:
#   "cdn"  -> 文件小 (几十 KB), 但浏览器需联网加载 plotly.js
#   True   -> 完全离线可用, 但文件约 3.5 MB (内嵌 plotly.js)
INCLUDE_PLOTLYJS = "cdn"

OUTCOME_COLORS = {
    "swish": "#2ca02c",      # 绿
    "rim-in": "#ff7f0e",     # 橙
    "board-in": "#1f77b4",   # 蓝
    "miss": "#9e9e9e",       # 灰
}
OUTCOME_LABELS = {
    "swish": "空心", "rim-in": "弹框进",
    "board-in": "打板进", "miss": "未进",
}
FALLBACK_COLOR = "#9e9e9e"
FALLBACK_LABEL = "未知"


def compute_trajectory(angle_deg, backspin, release_pos=RELEASE_POS,
                       speed=SPEED, downsample=DOWNSAMPLE):
    """跑一次投篮, 返回 (xs, ys, outcome)。downsample>=1 (改进校验)。"""
    if int(downsample) < 1:
        raise ValueError(f"downsample must be >= 1, got {downsample!r}")
    downsample = int(downsample)
    pos = np.asarray(release_pos, dtype=float)
    if pos.shape != (3,) or not np.all(np.isfinite(pos)):
        raise ValueError(f"release_pos must be a finite shape (3,) vector, got {pos!r}")
    speed = float(speed)
    if not np.isfinite(speed) or speed <= 0.0:
        raise ValueError(f"speed must be positive finite, got {speed!r}")
    v0 = release_velocity(speed, angle_deg)
    res = simulate_shot(pos, v0, backspin)
    xs = res["states"][:, 0][::downsample]
    ys = res["states"][:, 1][::downsample]
    return xs, ys, res["outcome"]


def _scatter_for(ang, back, xs, ys, outcome):
    """单条轨迹的 Scatter (frame / 初始图共用构造, 与原版字段逐项一致)。"""
    if outcome not in OUTCOME_COLORS:
        print(f"  警告: 模型给出未知结局 {outcome!r} "
              f"(θ={ang:.0f}°, ω={back:.0f}) — 用灰色兜底, HTML 仍可生成")
    return go.Scatter(
        x=xs, y=ys, mode="lines",
        line=dict(color=OUTCOME_COLORS.get(outcome, FALLBACK_COLOR), width=2.5),
        name=f"{ang:.0f}_{back:.0f}",
        hovertemplate=(
            f"θ={ang:.0f}°  ω={back:.0f} rad/s  "
            f"结局: {OUTCOME_LABELS.get(outcome, FALLBACK_LABEL)}<extra></extra>"),
    )


def main(out_html: str = OUT_HTML, include_plotlyjs: str | bool = INCLUDE_PLOTLYJS,
         angles_deg=None, backspins=None, release_pos=RELEASE_POS,
         speed=SPEED, downsample=DOWNSAMPLE):
    """生成 HTML 浏览器。返回输出路径。 (扫描/布局构造与原版逐字段一致)"""
    angles_deg = np.asarray(angles_deg if angles_deg is not None
                            else ANGLES_DEG, dtype=float).reshape(-1)
    backspins = np.asarray(backspins if backspins is not None
                           else BACKSPINS, dtype=float).reshape(-1)
    if angles_deg.size == 0 or backspins.size == 0:
        raise ValueError("角度/后旋网格不能为空")

    out_path = Path(out_html)
    if str(out_path.parent) not in ("", ".") and not out_path.parent.is_dir():
        raise FileNotFoundError(f"输出目录不存在: {out_path.parent}")

    # 1) 扫描并计算所有轨迹 (后旋外层 → 拖动滑块时主要扫过角度, 视觉变化更明显)
    trajs = []
    for back in backspins:
        for ang in angles_deg:
            xs, ys, outcome = compute_trajectory(ang, back, release_pos,
                                                 speed, downsample)
            trajs.append((ang, back, xs, ys, outcome))
    if not trajs:
        raise ValueError("没有产出任何轨迹 (网格为空?)")

    # 2) 每条轨迹一个 frame
    frames = [go.Frame(data=[_scatter_for(ang, back, xs, ys, outcome)],
                       name=f"{ang:.0f}_{back:.0f}")
              for ang, back, xs, ys, outcome in trajs]

    # 3) 初始图 (第一条轨迹) — 与原版一致: 无 name (原版初始 Scatter 未带 name)
    ang0, back0, xs0, ys0, out0 = trajs[0]
    fig = go.Figure(
        data=[go.Scatter(
            x=xs0, y=ys0, mode="lines",
            line=dict(color=OUTCOME_COLORS.get(out0, FALLBACK_COLOR), width=2.5),
        )],
        frames=frames,
    )

    # 4) 静态几何: 篮板 (竖线) + 篮筐 (横线), 存在 layout 里, 不随 frame 变化
    shapes = [
        dict(type="line",
             x0=BACKBOARD_X, y0=BACKBOARD_BOTTOM,
             x1=BACKBOARD_X, y1=BACKBOARD_TOP,
             line=dict(color="black", width=3)),
        dict(type="line",
             x0=RIM_CENTER[0] - RIM_RADIUS, y0=RIM_HEIGHT,
             x1=RIM_CENTER[0] + RIM_RADIUS, y1=RIM_HEIGHT,
             line=dict(color="red", width=4)),
    ]

    # 5) 滑块 steps
    steps = [dict(
        method="animate",
        args=[[f"{ang:.0f}_{back:.0f}"],
              {"frame": {"duration": 0, "redraw": True},
               "mode": "immediate",
               "transition": {"duration": 0}}],
        label=f"{ang:.0f}/{back:.0f}",
    ) for ang, back, _xs, _ys, _outcome in trajs]

    sliders = [dict(
        active=0,
        steps=steps,
        currentvalue={"prefix": "出手参数 (角度°/后旋 rad/s): "},
        pad=dict(t=60),
    )]

    fig.update_layout(
        title="篮球轨迹浏览器 — 拖动滑块查看不同出手参数",
        xaxis=dict(title="x (m)  [投手 → 篮筐]", range=[-4.7, 0.6]),
        yaxis=dict(title="y (m)", range=[0.0, 4.6]),
        shapes=shapes,
        sliders=sliders,
        showlegend=False,
        height=640,
    )

    # 颜色图例说明
    fig.add_annotation(
        text="绿=空心(swish)  橙=弹框进(rim-in)  蓝=打板进(board-in)  灰=未进(miss)",
        xref="paper", yref="paper", x=0.99, y=0.98,
        xanchor="right", yanchor="top",
        showarrow=False, font=dict(size=11),
        bgcolor="rgba(255,255,255,0.7)",
    )

    fig.write_html(str(out_path), include_plotlyjs=include_plotlyjs)
    kind = "CDN (小文件, 需联网)" if include_plotlyjs == "cdn" else "内嵌 (离线可用)"
    print(f"已生成 {out_path}  ({len(trajs)} 条轨迹, plotly.js={kind}, "
          f"{'*_improved 链路' if _CHAIN == 'improved' else '主流程链路'})")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="生成交互式篮球轨迹 HTML (make_interactive.py 的改进版)")
    ap.add_argument("--out", default=OUT_HTML, help="输出 HTML 路径")
    ap.add_argument("--offline", "--embed", action="store_true",
                    help="内嵌 plotly.js (文件大, 完全离线)")
    ap.add_argument("--cdn", action="store_true", help="用 CDN (默认)")
    ns = ap.parse_args()
    include = True if ns.offline else INCLUDE_PLOTLYJS
    main(out_html=ns.out, include_plotlyjs=include)
