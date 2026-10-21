# PROJECT_CONTEXT —— 给 AI 助手的上下文记忆

> 这是 `PROJECT_CONTEXT.md` 的改进版（2026-10-21），原版文件保留在同目录。
> 主要变更：反映 `*_improved.py` 链已合并回单一模块（commit `bc7b400` 精简三套.py）后的
> 现状；补齐 2D 层常数与接口（`*_2D` / `*_2d` 函数）、2D 扫描与 HTML 浏览器、
> validation 新 CLI、`data_validation/` 暂存状态与更新后的 To-Do。
> 代码实现细节以各 `.py` 文件内的 docstring 为准；这里只放关键设定、接口与当前结论。

## 1. 项目概览

本项目是一个纯物理（无机器学习）篮球投篮模拟。给定出手点、出手速度向量和后旋角速度，
用 RK4 积分求解飞行轨迹，受力包括重力、二次空气阻力和马格努斯升力；并与篮板、篮筐发生刚性碰撞
（恢复系数 e = 0.7）。模型输出四类结局：`swish` / `rim-in` / `board-in` / `miss`，并生成命中概率热力图、
罚球/三分球轨迹对比和验证误差量化。仓库同时包含一个常数不同的独立 2D 交互演示模型
（`basketball_shot_2d.py`），其库化版本（`*_2D`/`*_2d`）已并入 `physics.py` / `collision.py` /
`simulation.py` / `experiment.py`，两套模型并存于同一文件、绝不可混用常数或结论（见 README §4）。

## 2. 核心物理设定

### 2.1 3D 主流程

**坐标系（右手系，SI 单位）**
- `x` 从投手指向篮筐；`y` 竖直向上；`z` 侧向。
- 篮板在 `x = 0`，投手在 `-x` 侧；筐心 `RIM_CENTER = (-0.375, 3.05, 0)`。

**后旋方向定义**
- 纯后旋取 `ω = (0, 0, +ω)`；`ω × v` 的 `y` 分量为正 → 产生向上升力。

**NBA 场地常数（collision.py）**
- `RIM_HEIGHT = 3.05 m`，`RIM_DIAMETER = 0.45 m`（`RIM_RADIUS = 0.225 m`）
- `RIM_TO_BOARD = 0.375 m`（筐心到篮板面）
- 篮板：宽 1.8 m、高 1.05 m、下沿 2.9 m（竖直平面 `x = 0`）
- `RESTITUTION e = 0.7`（分面参数 `BACKBOARD_RESTITUTION` / `RIM_RESTITUTION`，默认同为 0.7；
  `TANGENTIAL_RETENTION = 1.0` 默认无切向损失）

**物理常数（physics.py）**
- `G = 9.81`，`RHO_AIR = 1.225`，`C_D = 0.50`，`C_L0 = 1.00`
- `BALL_MASS = 0.624 kg`，`BALL_RADIUS = 0.12 m`

**三力**
- 重力：`F_g = (0, -m·g, 0)`
- 二次阻力：`F_d = -0.5·ρ·C_d·A·|v|·v`
- 马格努斯：`F_M = 0.5·ρ·A·C_L0·R·(ω × v)`
  （等价于升力系数形式，`C_L = C_L0·R|ω|/|v|`）

**得分判据**
- 球心向下穿过 `y = 3.05` 平面，且水平距筐心 `<= RIM_RADIUS - BALL_RADIUS = 0.105 m`
- 从未碰筐/篮板 → `swish`；只碰筐 → `rim-in`；碰过篮板 → `board-in`；否则 `miss`。
- 结局按 `contacts` 碰撞序列细分，匹配计划书中的 4 类结局设定。

### 2.2 2D 演示/扫描层（同文件内的 `*_2D` 常数，冻结自课程 deck）

- `BALL_MASS_2D = 0.60`，`RHO_AIR_2D = 1.204`，`C_D_2D = 0.47`，`C_L_2D = 0.20`（固定升力系数）
- `DRAG_PARAM_2D = 0.02134 /m`，`MAGNUS_PARAM_2D = 1.0895e-3`
- `RIM_RADIUS_2D = 0.2287`（内径 45.7 cm），板面 = 筐后沿 + `BOARD_OFFSET_2D = 0.15`
- `FREE_THROW_2D = 4.60`，`THREE_POINT_2D = 6.75`
- 碰撞：法向 `RESTITUTION_NORMAL_2D = 0.70` + 切向 `RESTITUTION_TANGENTIAL_2D = 0.85`；
  板面穿越触发 + 接触高度窗口 `[2.75, 3.85]`，篮板反弹上限 4 次；筐沿按前后两个圆点端处理
- 进球判据：穿筐面 + 筐口内沿两侧各 12 mm（`OPENING_MARGIN_2D = 0.012`）
- 后旋只取飞行平面内分量 `ω_z = spin·sin(θ)`
- 2D 结局名 `SWISH` / `BANK-IN` / `RATTLE-IN`（+ 各种 miss 描述），经
  `canonical_outcome_2d()` 归一化对接 3D 四分类：BANK-IN→board-in、RATTLE-IN→rim-in
- 单文件交互器 `basketball_shot_2d.py` 与库版 2D 引擎（`simulation.simulate_2d`）逐位同源

## 3. 代码接口

状态向量统一为 `[x, y, z, vx, vy, vz]`（6 维，3D）；2D 为 `[x, y, vx, vy]`。

### physics.py
- `rk4_step(state(6,), dt, omega(3,)) -> (6,)`
- `rk4_step_batch(state(N,6), dt, omega) -> (N,6)`（向量化）
- `integrate(release_pos(3,), release_vel(3,), backspin_rate, dt=1e-3, t_max=3.0, stop=None, stop_at_floor=True) -> (times, states(N,6))`
- `release_velocity(speed, angle_deg, azimuth_deg=0) -> (3,)`，`spin_vector(backspin_rate) -> (0,0,+rate)`
- 2D 层：`spin_in_plane_2d`、`acceleration_2d`、`rk4_step_2d`、`ideal_arc_coeffs_2d`、
  `ideal_parabola_2d`、`vacuum_aim_2d`（真空最小速率）、`air_load_2d`、`curvature_flatten_pct_2d`
  （v=0 / 90° 等退化输入干净报错，原版会 ZeroDivisionError / 返回 inf）

### collision.py
- `detect_backboard(pos, ball_radius=...) -> Collision | None`（矩形面-球，含边/角最近点）
- `detect_rim(pos, ...) -> Collision | None`（圆环-球）
- `detect_any(pos) -> Collision | None`（兼容接口，取第一个接触）
- `detect_all(pos) -> list[Collision]`（同位置全部接触，backboard-then-rim 稳定顺序）
- `Collision` 字段：`kind, normal(3,), penetration, contact(3,)`
- `reflect(vel, normal, e=..., tangential_retention=...) -> (3,)`；`restitution_for(kind)`
- `resolve(pos, vel, collision, correct_position=True, restitution=None, ...)`
- `resolve_contacts(...)`：多接触有限轮顺序响应 + 迭代位置校正（饱和时不抖动）
- 批量：`detect_backboard_batch`、`detect_rim_batch`、`detect_all_batch`
- 2D 几何/响应层：`hoop_geometry_2d`、`reflect_2d`、`cross_board_plane_2d`、`bounce_off_board_2d`、
  `rim_edge_gap_2d`、`detect_rim_edges_2d`、`bounce_off_rim_edge_2d`、`detect_scoring_cross_2d`、
  `classify_outcome_2d`、`canonical_outcome_2d`
- `python collision.py` 打印 4 组 3D 示例 + 5 组 2D 示例

### simulation.py
- `simulate_shot(release_pos, release_vel, backspin_rate, dt=1e-3, t_max=4.0, max_bounces=50) -> dict`
  dict 键：`outcome`、`reason`、`contacted`、`contacts`、`times`、`states`
- `save_trajectory_csv(path, times, states)`
- 库版 2D 引擎：`simulate_2d(h0, angle, spin, v, dist, air=True, ...)`（与交互器逐位一致）、
  `fit_segments_2d`、`save_2d_csv`、`readout_2d`
- `python simulation.py`：单发 3D 罚球样例 -> `trajectory.csv`；再跑 6 个 2D 文档场景自检
  -> `trajectory_2d.csv`

### experiment.py
- `batch_simulate(positions(N,3), velocities(N,3), backspin_rate) -> made/swish/rim_in/board_in`
- `batch_simulate_2d(...)`、`find_band_2d`、`run_sweep_2d`（每格最宽必中速度窗口统计）
- `run_sweep(out_csv="data.csv", seed=0)`；`run_three_point_sweep`；`run_sweep_mp`（多进程）
- 3D 网格：罚球 角度 `30–70°` × 后旋 `0–60 rad/s`（各 17 点），三分球 角度 `36–60°` × 后旋 `0–60`（各 17 点），
  每格 100 次抖动（σ 角度 1°、速率 0.1 m/s）；罚球 7.5 m/s @ 4.57 m，三分 9.5 m/s @ 6.75 m
- CSV 列：`angle, backspin, p_make, p_swish, p_rim_in, p_board_in` + 扫描配置元数据列
  （`rim_distance_m`、`nominal_speed_m_s`、`seed`、抖动 σ、网格范围等，每行可追溯）
- 2D 网格：`_2D_ANGLES = 30–70°`（17）、`_2D_BACKSPINS = 0–40`（17，与 UI 滑块上限一致），
  速度 150 采样点 5.5–14.5 m/s（与 UI SCAN WINDOW 同规则）
- CLI：`free` / `three` / `2d` / `--mp` / `--selfcheck`；默认无参 = 四套全跑

### plotting.py
- `plot_make_probability` / `plot_make_probability_comparison` / `plot_outcome_breakdown`
- `plot_trajectory_comparison` / `plot_trajectory_comparison_three` / `plot_free_vs_three`
- `plot_all(out_dir)`：一次出 7 张图；CLI `python plotting.py`（默认全画）、`breakdown`、`selfcheck`

### validation.py
- CSV 格式：`shot_id, release_x, release_y, release_z, v0x, v0y, v0z, backspin, actual_outcome`
- `actual_outcome`：命中(具体子类) = `swish` / `rim-in` / `board-in`；命中(旧标签，仅二分类) = `bounce-in` / `made` / `in`；未中 = `miss` / `out` / `no`
- `predict(shot) -> (predicted_outcome, predicted_binary)`；单条参数非法记 error 不致命
- `run_validation(csv_path="dummy_data.csv")`：二分类指标（一致率 + Wilson 95% CI + precision/recall/specificity/F1/MCC + Cohen's kappa + 无信息率基线）与 4 类多分类混淆矩阵
- `wilson_ci(k, n, z=1.96)`（含参数校验）
- `make_dummy_data(csv_path="dummy_data.csv", n=20, seed=0, correlated=False)`
- CLI：`--make-dummy [--correlated]`、`[数据.csv]`、`selfcheck`（临时目录全链路断言 100%）

### make_interactive.py / basketball_interactive.html
- `main(out_html, include_plotlyjs, angles_deg, backspins, release_pos, speed, downsample)`
- CLI：默认 CDN 版；`--offline`（内嵌 plotly.js，约 3.5 MB）；`--out <html>`
- 扫描：角度 `40–60°`（步 5）× 后旋 `0–40 rad/s`（步 10）= 25 帧，固定 7.5 m/s、
  出手点 `(-4.57, 2.0, 0)`，轨迹 `DOWNSAMPLE=4`；结局色 swish 绿 / rim-in 橙 / board-in 蓝 / miss 灰，
  未知结局灰色兜底 + 警告

## 4. 当前成果（已跑通）

- **命中概率峰值（3D 罚球）**：`55°`、`45 rad/s`，`P ≈ 0.77`；三分 `48°`、`48.8 rad/s`，`P ≈ 0.80`
  （后旋维度存在宽平台 ~15–45 rad/s，具体峰值随随机种子略有浮动；两套扫描名义速度不同，
  峰值水平不可当同难度对比）
- **轨迹偏差**：以真空仰角（约 55.7°）出手，真实（阻力+后旋）轨迹到达筐面时
  **偏低约 40.2 cm**；同样仰角/后旋下，**三分球（6.75 m）偏低约 117.4 cm**，
  比罚球多偏 77.2 cm（`plotting.py`，`free_vs_three_drag.png`）
- **单发样例**：7.5 m/s、51°、23 rad/s → `swish`（穿过筐面水平偏移 r=0.055 m）
- **验证链路**：dummy 随机标签下 Agreement ≈ 35%，Cohen's kappa ≈ −0.18
  （随机基线，无意义）；`--correlated` 自洽模式 ≈ 100%、kappa ≈ 1.0；20 发样本的一致率
  Wilson 95% CI 约 [18%, 57%]，说明小样本下裸比例不确定度很大，须报告区间
- **2D 层**：6 个文档场景（演示 GIF 同源参数）经 `--check` / `python simulation.py` 全部复现；
  2D 速度窗口数据（`data_2d*.csv`）与交互器 `SCAN WINDOW` 同规则
- **可复现性**：原 `*_improved.py` 链合并回单模块时逐位校验（CSV/图/指标与改进前一致），
  `test_core.py` / `test_collision.py` / `test_experiment.py` 全绿
- **真实数据暂存（data_validation/）**：SportVU 风格轨迹抽取 24,073 行（6 列，时间戳精度丢失、
  轴约定未确认）+ 5 条出手位置/速度初值（单位/来源未记录）；原 `*_template.csv` 已从仓库移除，
  字段规范与验收步骤见 `data_validation/DATA_SPECIFICATION.md`（新版）——**尚不是可运行的验证输入**

## 5. To-Do（下一步）

- [ ] 给 SportVU 抽取件恢复原始时间戳精度、确认源坐标轴/原点/单位约定（见 DATA_SPECIFICATION.md §3/§7）
- [ ] 为每条 shot 补齐 `backspin` 与出手三分量（60 fps 逐帧追踪或来源标注），再跑
      `validation.py` 得到真实一致率 + 置信区间 + kappa
- [ ] 用文献速率标定三分球出手速度后重跑三分扫描，使罚球/三分峰值水平可直接比较
- [ ] 写最终报告（方法、结果、局限、伦理）；补全 `Report_Draft.md` §3.3 的真实数据数字
- [ ] （可选）调 `C_L0` 使最优后旋更接近计划书的 23 rad/s
- [ ] （可选）用 `pip freeze` 固定精确依赖版本
