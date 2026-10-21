"""
make_interactive.py — 生成交互式篮球轨迹浏览器 basketball_interactive.html。

用 Plotly 先跑一个 (出手角度 × 后旋速率) 参数扫描, 把每条飞行轨迹存成一个 frame,
再用 frames + sliders 生成带滑块的交互式 HTML。队友拿到这一个 HTML 文件,
浏览器双击打开, 拖动滑块即可查看不同出手参数下的轨迹与结局 (颜色区分结局)。

依赖:  numpy, plotly
安装:  pip install numpy plotly
用法:  python make_interactive.py   ->  生成 basketball_interactive.html
"""

import numpy as np

try:
    import plotly.graph_objects as go
except ImportError:
    raise SystemExit("缺少 plotly, 请先运行:  pip install plotly")

from simulation import simulate_shot
from physics import release_velocity
from collision import (
    RIM_CENTER, RIM_HEIGHT, RIM_RADIUS,
    BACKBOARD_X, BACKBOARD_BOTTOM, BACKBOARD_TOP,
)

# ---------------------------------------------------------------------------
# 扫描参数
# ---------------------------------------------------------------------------
ANGLES_DEG = np.arange(40.0, 61.0, 5.0)      # 出手角度 40..60°
BACKSPINS = np.arange(0.0, 41.0, 10.0)       # 后旋 0..40 rad/s
RELEASE_POS = (-4.57, 2.0, 0.0)              # 出手点 (标准罚球)
SPEED = 7.5                                  # 出手速率 [m/s]
DOWNSAMPLE = 4                               # 每隔几个轨迹点取 1 个, 控制 HTML 体积

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


def compute_trajectory(angle_deg, backspin):
    """跑一次投篮, 返回 (xs, ys, outcome)。"""
    v0 = release_velocity(SPEED, angle_deg)
    res = simulate_shot(RELEASE_POS, v0, backspin)
    xs = res["states"][:, 0][::DOWNSAMPLE]
    ys = res["states"][:, 1][::DOWNSAMPLE]
    return xs, ys, res["outcome"]


def main():
    # 1) 扫描并计算所有轨迹 (后旋外层 → 拖动滑块时主要扫过角度, 视觉变化更明显)
    trajs = []
    for back in BACKSPINS:
        for ang in ANGLES_DEG:
            xs, ys, outcome = compute_trajectory(ang, back)
            trajs.append((ang, back, xs, ys, outcome))

    # 2) 每条轨迹一个 frame
    frames = []
    for ang, back, xs, ys, outcome in trajs:
        name = f"{ang:.0f}_{back:.0f}"
        frames.append(go.Frame(
            data=[go.Scatter(
                x=xs, y=ys, mode="lines",
                line=dict(color=OUTCOME_COLORS[outcome], width=2.5),
                name=name,
                hovertemplate=(
                    f"θ={ang:.0f}°  ω={back:.0f} rad/s  "
                    f"结局: {OUTCOME_LABELS[outcome]}<extra></extra>"),
            )],
            name=name,
        ))

    # 3) 初始图 (第一条轨迹)
    ang0, back0, xs0, ys0, out0 = trajs[0]
    fig = go.Figure(
        data=[go.Scatter(
            x=xs0, y=ys0, mode="lines",
            line=dict(color=OUTCOME_COLORS[out0], width=2.5),
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
    steps = []
    for ang, back, xs, ys, outcome in trajs:
        name = f"{ang:.0f}_{back:.0f}"
        steps.append(dict(
            method="animate",
            args=[[name],
                  {"frame": {"duration": 0, "redraw": True},
                   "mode": "immediate",
                   "transition": {"duration": 0}}],
            label=f"{ang:.0f}/{back:.0f}",
        ))

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

    fig.write_html("basketball_interactive.html", include_plotlyjs=INCLUDE_PLOTLYJS)
    kind = "CDN (小文件, 需联网)" if INCLUDE_PLOTLYJS == "cdn" else "内嵌 (离线可用)"
    print(f"已生成 basketball_interactive.html  ({len(trajs)} 条轨迹, plotly.js={kind})")


if __name__ == "__main__":
    main()
