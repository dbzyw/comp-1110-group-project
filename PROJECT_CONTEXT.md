# PROJECT_CONTEXT —— 给 AI 助手的上下文记忆

> 代码实现细节以各 `.py` 文件内的 docstring 为准；这里只放关键设定、接口与当前结论。

## 1. 项目概览

本项目是一个纯物理（无机器学习）篮球投篮模拟。给定出手点、出手速度向量和后旋角速度，
用 RK4 积分求解飞行轨迹，受力包括重力、二次空气阻力和马格努斯升力；并与篮板、篮筐发生刚性碰撞
（恢复系数 e = 0.7）。模型输出四类结局：`swish` / `rim-in` / `board-in` / `miss`，并生成命中概率热力图、
罚球/三分球轨迹对比和验证误差量化。仓库同时包含一个常数不同的独立 2D 交互演示模型
（`basketball_shot_2d.py`），其库化版本（`*_2D`/`*_2d`）已并入 `physics.py` / `collision.py` /
`simulation.py` / `experiment.py`，两套模型并存于同一文件、绝不可混用常数或结论（见 README §4）。

### Blender 的职责与预测流程

- **预测由 Python 3D 物理引擎完成**：`simulation.simulate_shot()`根据释放位置、速度和后旋积分轨迹；若球心向下穿过 NBA 筐顶平面 `y = 3.048 m` 且水平距开口中心不超过 `RIM_RADIUS - BALL_RADIUS ≈ 0.10935 m`，则判为 made，否则判为 miss。made 再根据接触历史细分为 `swish` / `rim-in` / `board-in`。`validation.py`对符合 CSV 规范且带观测标签的记录调用该模拟并比较结果。
- **Blender 是 3D 可视化工具，不会自行做物理预测或验证**。它呈现由模拟算出的轨迹和结局。`blender_3d/find_shots.py`调用物理引擎搜寻三种演示用的 made 轨迹，输出 `traj_*.csv` 和 `shots.json`；`build_blender.py`读取这些文件，生成关键帧、`.blend` 场景、静帧和可选 MP4。当前场景没有 miss 演示。
- 对新初始条件，直接调用 `simulation.simulate_shot()`获得预测轨迹与结局；需要与已记录结果比较时，使用带 `actual_outcome` 的 CSV 运行 `python validation.py <shots.csv>`。若需要 Blender 动画，必须再把目标预测轨迹提供给 Blender 渲染流程。当前 `build_blender.py`只消费预制的三组命中演示轨迹，并不直接读取任意验证 CSV 或输出，因此不能把现有 Blender 场景当作任意 CSV 的自动可视化接口。
- 从仓库根目录重建当前演示：`python blender_3d\find_shots.py`，再运行 `blender -b -noaudio --python blender_3d\build_blender.py`。Blender 5.x 用于脚本构景与渲染；MP4 合成还需要 `ffmpeg` 在 `PATH` 中。

## 2. 核心物理设定

### 2.1 3D 主流程

**坐标系（右手系，SI 单位）**
- `x` 从投手指向篮筐；`y` 竖直向上；`z` 侧向。
- 篮板正面在 `x = 0`，投手在 `-x` 侧；NBA 篮筐开口中心 `(-0.381, 3.048, 0)`，钢管中心线位于管半径以内。

**后旋方向定义**
- 纯后旋取 `ω = (0, 0, +ω)`；`ω × v` 的 `y` 分量为正 → 产生向上升力。

**NBA 场地常数（collision.py）**
- `RIM_HEIGHT = 3.048 m`（10 ft 筐顶高度）；NBA 净开口直径 `0.4572 m`（18 in），半径 `0.2286 m`
- 钢管直径取 `0.018 m`（FIBA 16–20 mm 规格区间中点）；`RIM_CENTERLINE_RADIUS = 0.2376 m`
- 开口中心到篮板正面 `RIM_TO_BOARD = 0.381 m`（6 in 板面间隙 + 9 in 开口半径）
- NBA 篮板：宽 1.8288 m、高 1.0668 m、下沿 2.8956 m（竖直平面 `x = 0`）；Blender 板厚取 12.7 mm
- `RESTITUTION e = 0.7`（分面参数 `BACKBOARD_RESTITUTION` / `RIM_RESTITUTION`，默认同为 0.7；
  `TANGENTIAL_RETENTION = 1.0` 默认无切向损失）

**物理常数（physics.py）**
- `G = 9.80665`，`RHO_AIR = 1.225`，`C_D = 0.50`，`C_L0 = 1.00`
- `BALL_MASS = 22 oz ≈ 0.62369 kg`，`BALL_RADIUS = 29.5 in / (2π) ≈ 0.11925 m`

**三力**
- 重力：`F_g = (0, -m·g, 0)`
- 二次阻力：`F_d = -0.5·ρ·C_d·A·|v|·v`
- 马格努斯：`F_M = 0.5·ρ·A·C_L0·R·(ω × v)`
  （等价于升力系数形式，`C_L = C_L0·R|ω|/|v|`）

**得分判据**
- 球心向下穿过 `y = 3.048` 平面，且水平距开口中心 `<= RIM_RADIUS - BALL_RADIUS ≈ 0.10935 m`
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
- 3D 网格：罚球角度 `30–70°` × 后旋 `0–60 rad/s`（各 17 点），三分球角度 `36–60°` × 后旋 `0–60`（各 17 点），
  每格 100 次抖动（σ 角度 1°、速率 0.1 m/s）；罚球 7.5 m/s @ 15 ft from board face，三分 9.5 m/s @ NBA arc apex 23 ft 9 in from rim centre
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

- **命中概率峰值（3D 主流程，本次运行）**：罚球 `55°`、`45 rad/s`，`P = 0.77`
  （swish 0.52 / rim-in 0.15 / board-in 0.10）；三分 `45°`、`37.5 rad/s`，`P = 0.79`
  （该峰值格全部为 board-in）。两套扫描名义速度不同（7.5 vs 9.5 m/s），峰值水平不可当同难度对比。
- **轨迹偏差**：以真空仰角（约 56.0°）出手，真实（阻力+后旋）轨迹到达筐面时
  **偏低约 42.5 cm**；同样仰角/后旋下，**三分球（6.75 m）偏低约 119.5 cm**，
  比罚球多偏 77.0 cm（`plotting.py`，`free_vs_three_drag.png`）
- **单发样例**：7.5 m/s、51°、14.137167 rad/s → `swish`（穿过筐面水平偏移 r=0.015 m）
- **验证链路**：dummy 随机标签下 Agreement ≈ 35%，Cohen's kappa ≈ −0.18
  （随机基线，无意义）；`--correlated` 自洽模式 ≈ 100%、kappa ≈ 1.0；20 发样本的一致率
  Wilson 95% CI 约 [18%, 57%]，说明小样本下裸比例不确定度很大，须报告区间
- **2D 层**：6 个文档场景（演示 GIF 同源参数）经 `--check` / `python simulation.py` 全部复现；
  2D 速度窗口数据（`data_2d*.csv`）与交互器 `SCAN WINDOW` 同规则；本次最宽窗口为罚球
  0.3020 m/s（47.5°、35 rad/s）和三分 0.2416 m/s（52.5°、5 rad/s），中点结局均为 `BANK-IN`
- **可复现性**：原 `*_improved.py` 链合并回单模块时逐位校验（CSV/图/指标与改进前一致），
  `test_core.py` / `test_collision.py` / `test_experiment.py` 全绿
- **真实数据暂存（data_validation/）**：SportVU 风格轨迹抽取 24,073 行（6 列，时间戳被导出压平成
  同一圆整值、轴约定未确认）+ 5 条出手位置/速度初值 + 30 条筛选位置/速度数据（源单位、坐标轴与来源仍未确认）
  + 原始投篮数据集 300 行（仅二元 `Shot_Result`）。数据已分离：`valid_data_2D.csv` 有 300 行，
  由 `data_prep.py` 以 straight-on 假设生成（`release_z = v0z = 0`）；`valid_data_3D.csv` 有
  35 行暂定 3D 输入，正 `x_m` 已取负且 `z_m`/`y_m` 暂映射为高度/侧向位置。两份 CSV 均可被
  `validation.py` 解析，但并非实测验证；字段规范见 `data_validation/DATA_SPECIFICATION.md`。
- 历史验证报告（NBA 几何/球参数调整前）：2D 近似使用 source speed/angle 后为 153/300 agreement，
  暂定 3D 输入为 0/35 agreement。由于物理常数现已更新，两份报告不是当前模型结果；两者也均不应视为经验结论。

## 5. To-Do（下一步）

- [ ] 给 SportVU 抽取件恢复原始时间戳精度、确认源坐标轴/原点/单位约定（见 DATA_SPECIFICATION.md §3/§7）
- [ ] 处理 `valid_data_3D.csv` 的假设问题：核对/剔除 IDs 301–335（源坐标/单位、`y_m` 映射和 `made` 为预设），
      把 `valid_data_2D.csv` 的合成参数换成实测/有来源的出手几何与 backspin 之后，一致率才可作为经验结论引用
- [ ] 为每条 shot 补齐 `backspin` 与出手三分量（60 fps 逐帧追踪或来源标注），再跑
      `validation.py` 得到真实一致率 + 置信区间 + kappa
- [ ] 用文献速率标定三分球出手速度后重跑三分扫描，使罚球/三分峰值水平可直接比较
- [ ] 写最终报告（方法、结果、局限、伦理）；补全 `Report_Draft.md` §3.3 的真实数据数字
- [ ] （可选）用有来源的旋转率数据重新校准 `C_L0`；当前默认后旋按 `data_prep.py` 的 2.25 RPS 中值设定（14.137167 rad/s）
- [ ] （可选）用 `pip freeze` 固定精确依赖版本
