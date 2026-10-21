# 2D 投篮模拟的物理与实现笔记（basketball_shot_2d.py）

> 对应代码：根目录 `basketball_shot_2d.py`。本文记录该文件的模型设定、数值方法与实现要点，
> 以及它与 3D 主流程（`physics.py` / `collision.py` / `simulation.py`，见
> [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)）的**常数差异**——两套模型各自独立，混用结论前先看 §7。

## 目录

1. 模型概览
2. 常数
3. 运动方程与积分
4. 碰撞模型
5. 拟合弧线与真空对照
6. SCAN WINDOW 与交互层
7. 与 3D 主流程的差异
8. 已知简化
9. 库化 2D 层与自检入口

## 1. 模型概览

单文件 2D（x–y 竖直平面）投篮模拟：给定出手高度、仰角、后旋、出手速率和篮筐距离，
用定步长 RK4 积分含重力、二次空气阻力与马格努斯升力的运动方程，逐步检测篮板/篮筐碰撞，
输出轨迹、结局（`SWISH` / `BANK-IN` / `RATTLE-IN` / 各种 miss）与碰撞记录。
附带一个 matplotlib 交互 UI（滑块 + 按钮 + 动画 + 读出面板）。

## 2. 常数（代码顶部"frozen model constants"，`physics.py` 里有同名 `*_2D` 对照）

| 符号 | 值 | 含义 |
|---|---|---|
| `R` | 0.12 m | 球半径 |
| `M` | 0.60 kg | 球质量 |
| `RHO` | 1.204 kg/m³ | 空气密度（20 °C） |
| `CD` | 0.47 | 阻力系数（球体典型值） |
| `CL` | 0.20 | 升力系数（马格努斯项） |
| `EN` | 0.70 | 碰撞法向恢复系数（`RESTITUTION_NORMAL_2D`） |
| `ET` | 0.85 | 碰撞切向恢复系数（`RESTITUTION_TANGENTIAL_2D`） |
| `YR` | 3.05 m | 筐沿高度 |
| `RIM_R` | 0.2287 m | 筐口半径（内径 45.7 cm，`RIM_RADIUS_2D`） |
| `BOARD_OFF` | 0.15 m | **篮板面**到筐后沿的距离（真实板面 = 后沿 + 0.15 m；代码里与球心比较的"穿越参考面" `xbc = xB + 0.15 − R`，即后沿 + 0.03 m，见 §4） |
| `FT_DIST` / `PT_DIST` | 4.60 / 6.75 m | 罚球 / 三分距离 |
| `BD` | 0.02134 /m | 合并后的阻力参数 `½ρC_D A / M`（A = π·0.12² = 0.045238 m² → 0.5·1.204·0.47·0.045238/0.60） |
| `BM` | 1.0895e-3 | 合并后的马格努斯参数 `½ρC_L A R / M`（0.5·1.204·0.20·0.045238·0.12/0.60） |

两个合并参数直接写在 `physics.py` 的 `DRAG_PARAM_2D` / `MAGNUS_PARAM_2D` 上（`python physics.py`
会打印它们并与 3D 值并排对照）。

## 3. 运动方程与积分

状态向量 `s = [x, y, vx, vy]`，导数：

```
ẍ = −BD·|v|·vx + BM·ωz·vy
ÿ = −g    −BD·|v|·vy − BM·ωz·vx
```

其中 `ωz = spin·sin(θ)`——后旋只有投影到飞行平面内的分量参与马格努斯项；
`ω × v` 展开后升力垂直于速度、指向弧线外侧（后旋 → 升力向上）。

积分：**定步长 RK4，dt = 1 ms，最长 4 s**。每步除推进状态外还做三件事：
记录最高点、线性插值求球**首次穿过筐面平面**时的高度 `plane_h`（供"短了/长了"判据）、
碰撞检测（§4）。

## 4. 碰撞模型

**篮板**（球心穿越参考面 `x = xbc`，接触高度窗口 `[YR−0.30, YR+0.80] = [2.75, 3.85] m`，
最多 4 次）：真实板面在筐后沿 +0.15 m 处，而碰撞按"球面触板"判断，所以代码比较的是
球心参考面 `xbc = xB + BOARD_OFF − R`（后沿 + 0.03 m）。只在某一步内球心**实际穿越**
该参考面时触发——用步内线性插值求穿越点位置和速度，然后直接把状态放到穿越点并按
法向/切向恢复系数反弹：`vx → −EN·vx`，`vy → ET·vy`。因为以"球心穿越"为触发条件，
擦板而过（从正面飞到板后）的球不会被误反弹，会继续飞到板后落地
（`past the board, lands behind`）。接触记录含进入/离开速度与 front/back 面标注，
供读出面板显示。

**筐沿**（前后两个端点 `xF`、`xB`，视为两个刚性圆点）：球心与端点距离 `< R`（且 > 1e-9）
时，沿接触法线做反弹——法向分量乘 `−EN`、切向分量乘 `ET`，并把球心推回到接触面外
（去穿透）。只在法向速度朝内（`vdn < 0`）时触发，避免球离开筐沿时二次触发。

**进球判据**：球心从上方穿过 `y = YR`（`vy < 0`），且水平位置在
`(xF + 12 mm, xB − 12 mm)` 内——两侧各留 12 mm 是筐口内沿的余量。
按碰撞历史分类：无碰撞 → `SWISH`；只碰板 → `BANK-IN`；碰过筐 → `RATTLE-IN`。

**miss 分类**（落地条件：球心 `y < 0.10 m`；分支按此顺序判定，字符串与代码逐字一致）：

1. 碰过板 → `off the board, out`；
2. 未碰板但碰过筐 → `off the rim, out`；
3. 最远 `x` 越过参考面 + 2 cm → `past the board, lands behind`；
4. 有 `plane_h` 且穿筐面时**低于** 3.05 → `long miss, past the hoop`；
5. 有 `plane_h` 且穿筐面时不低于 3.05（却没落进窗口）→ `short, low at the rim plane`；
6. `x` 从未到达 `dist`（`plane_h` 为空）→ `well short`。

注意第 4/5 条的标签与直觉相反（"到面时已低于筐沿"被标成长miss、"到面时不低于筐沿却没进"
被标成 short low），这是沿袭原版的命名怪癖；写报告时请引用分支条件而不是望文生义。

## 5. 拟合弧线与真空对照

`fit_segments` 把整条 RK4 轨迹按**篮板碰撞时刻**和**每个水平方向反转点**切分成段，
对每段做 `y(x)` 二次拟合（`np.polyfit`）。切段保证每段 x 单调，拟合才有意义；
反弹后的反向段会被翻转后再拟合。得到的每段二次系数**携带**了阻力、马格努斯升力
和全部反弹信息——UI 里青色弧线和读出面板的"轨迹函数"都是它。

对照组：`ideal_parabola` 给出同参数的真空抛物线解析式
`y = h0 + x·tanθ − g·x²/(2v²cos²θ)`；读出面板据此算"真空最小出手速度"
（`vacuum_aim`）和真实弧线比理想平缓的百分比。`v = 0` 或 `θ = 90°` 时干净地报
`ValueError`（原版在这里会 ZeroDivisionError；`--check` 会验证这一点）。

## 6. SCAN WINDOW 与交互层

- `find_band`：5.5–14.5 m/s 均匀取 150 个速度逐发 `simulate`，找全部连续"命中"区段，
  取最宽者，并在其中选一个已命中的中点速度回填到滑块。
- 性能要点：所有 artist（曲线、圆、矩形、文字）在 `init_scene` 里**只创建一次**，
  `update_scene` 只做 `set_data` / `set_center` / `set_bounds` 原地更新——
  早期版本每次拖滑块都 `ax.plot` 新曲线，旧线不会被清除，会越拖越卡、越叠越多。
  SHOOT 动画期间读出面板**不重绘**（只有主场景动），避免闪烁和数字跳动。
- 图例只在参数刷新时重建（`build_legend`），不在每帧重建。
- 参数入口统一走 `_finite()`：`simulate` / `find_band` 拒绝 NaN/inf；`dt` 必须为正。

## 7. 与 3D 主流程的差异（重要）

| 项 | basketball_shot_2d.py（本文） | physics.py / collision.py 主流程 |
|---|---|---|
| 维度 | 2D（x–y 平面） | 3D（6 维状态向量） |
| 球质量 | 0.60 kg | 0.624 kg |
| 空气密度 | 1.204 kg/m³ | 1.225 kg/m³ |
| C_D | 0.47 | 0.50 |
| 马格努斯 | 固定 `C_L = 0.20`，力 ∝ ω×v | `C_L0 = 1.00`，等价升力系数形式 |
| 碰撞恢复系数 | 法向 0.70 + **切向 0.85**（板面穿越触发） | 单一 e = 0.70（默认切向保留比例 1.0；步末嵌入检测 + 推出） |
| 筐口半径 | 0.2287 m（内径 45.7 cm） | 0.225 m（细圆环） |
| 板-筐几何 | 板面 = 后沿 + 0.15 m；球心参考面 = 后沿 + 0.03 m | 筐心距板面 0.375 m（板面与筐心间最近距离 0.15 m） |
| 进球判据 | 穿面 + 筐口内 12 mm 余量，结局 SWISH/BANK-IN/RATTLE-IN | 距筐心 ≤ RIM_RADIUS − BALL_RADIUS = 0.105 m，结局 swish/rim-in/board-in/miss |
| 定位 | 交互演示 / 教学可视化 | 批量实验、概率热力图、验证链路 |

两套代码的峰值参数（51°/23 rad/s 附近可命中）定性一致，但**具体数值不可直接互换**：
常数、碰撞模型和判据都不同。报告里引用数值时务必注明出处是哪套模型。2D 的三种
"进"名可用 `collision.canonical_outcome_2d()` 归一化到 3D 的 `swish/board-in/rim-in`
（miss → `miss`），仅用于统一标签空间。

## 8. 已知简化

- 2D：不考虑侧向偏移和侧旋。
- 筐沿建模为两个点质量端点，不是真实的圆环（侧向才需要环，2D 内两点已足够）。
- 篮板反弹上限 4 次、筐沿反弹无显式上限但每步去穿透，极端参数下长尾轨迹由 `max_t = 4 s` 兜底。
- 碰撞用恢复系数的冲量模型，不模拟球的形变和筐的振动。

## 9. 库化 2D 层与自检入口（合并后新增的事实）

同样的 2D 模型在合并后的主流程里有逐位同源的库版实现，改任何一边三处都要全跑：

- `physics.py`：`acceleration_2d` / `rk4_step_2d` / `ideal_parabola_2d` / `vacuum_aim_2d` /
  `air_load_2d` / `curvature_flatten_pct_2d`（`*_2D` 常数与上表一致）。
- `collision.py`：`hoop_geometry_2d`、板面穿越 `cross_board_plane_2d` / `bounce_off_board_2d`、
  前后缘 `detect_rim_edges_2d` / `bounce_off_rim_edge_2d`、得分穿越
  `detect_scoring_cross_2d`（窗口被 12 mm 余量关死时显式报错）与结局归一化。
- `simulation.py`：`simulate_2d`（完整碰撞循环，结局串与 UI 逐字一致）、`fit_segments_2d`、
  `save_2d_csv`、`readout_2d`；`python simulation.py` 会复现 6 个文档场景并写 `trajectory_2d.csv`。
- `experiment.py`：`batch_simulate_2d` / `find_band_2d` / `run_sweep_2d`——与 UI SCAN WINDOW
  相同的网格规则（150 个速度、最宽窗口、中点精确复算），产出 `data_2d.csv` /
  `data_2d_three.csv`；`python experiment.py --selfcheck` 逐字节校验。
- 无头自检：`python basketball_shot_2d.py --check`（6/6 文档场景 + `v=0` 拒绝），
  场景与 [SIMULATION_2D_DEMOS.md](SIMULATION_2D_DEMOS.md) 的参数表一一对应。
