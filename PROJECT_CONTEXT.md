# PROJECT_CONTEXT —— 给 AI 助手的上下文记忆

> 本文件是给「接手这个项目的另一个 AI 助手 / 协作者」快速建立上下文的精炼说明。
> 代码实现细节以各 `.py` 文件内的 docstring 为准；这里只放关键设定、接口与当前结论。

## 1. 项目概览

本项目是一个纯物理（无机器学习）篮球投篮模拟。给定出手点、出手速度向量和后旋角速度，
用 RK4 积分求解飞行轨迹，受力包括重力、二次空气阻力和马格努斯升力；并与篮板、篮筐发生刚性碰撞
（恢复系数 e = 0.7）。模型输出四类结局：`swish` / `rim-in` / `board-in` / `miss`，并生成命中概率热力图、罚球/三分球轨迹对比和验证误差量化。

## 2. 核心物理设定

**坐标系（右手系，SI 单位）**
- `x` 从投手指向篮筐；`y` 竖直向上；`z` 侧向。
- 篮板在 `x = 0`，投手在 `-x` 侧；筐心 `RIM_CENTER = (-0.375, 3.05, 0)`。

**后旋方向定义**
- 纯后旋取 `ω = (0, 0, +ω)`；`ω × v` 的 `y` 分量为正 → 产生向上升力。

**NBA 场地常数（collision.py）**
- `RIM_HEIGHT = 3.05 m`，`RIM_DIAMETER = 0.45 m`（`RIM_RADIUS = 0.225 m`）
- `RIM_TO_BOARD = 0.375 m`（筐心到篮板面）
- 篮板：宽 1.8 m、高 1.05 m、下沿 2.9 m（竖直平面 `x = 0`）
- `RESTITUTION e = 0.7`

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

## 3. 代码接口

状态向量统一为 `[x, y, z, vx, vy, vz]`（6 维）。

### physics.py
- `rk4_step(state(6,), dt, omega(3,)) -> (6,)`
- `rk4_step_batch(state(N,6), dt, omega) -> (N,6)`（向量化）
- `integrate(release_pos(3,), release_vel(3,), backspin_rate, dt=1e-3, t_max=3.0, stop=None, stop_at_floor=True) -> (times, states(N,6))`
- `release_velocity(speed, angle_deg, azimuth_deg=0) -> (3,)`
- `spin_vector(backspin_rate) -> (3,)`，即 `(0, 0, +rate)`

### collision.py
- `detect_backboard(pos(3,)) -> Collision | None`
- `detect_rim(pos(3,)) -> Collision | None`
- `detect_any(pos) -> Collision | None`（篮板优先）
- `Collision` 字段：`kind, normal(3,), penetration, contact(3,)`
- `reflect(vel(3,), normal(3,), e=0.7) -> (3,)`
- 批量：`detect_backboard_batch(pos(N,3)) -> (hit(N,), normal(N,3), pen(N,))`；`detect_rim_batch` 同

### simulation.py
- `simulate_shot(release_pos, release_vel, backspin_rate, dt=1e-3, t_max=4.0, max_bounces=50) -> dict`
  dict 键：`outcome`（`swish` / `rim-in` / `board-in` / `miss`）、`reason`、`contacted`、`contacts`、`times`、`states`
- `save_trajectory_csv(path, times, states)`

### experiment.py
- `batch_simulate(positions(N,3), velocities(N,3), backspin_rate) -> made(bool, N,)`
- `run_sweep(out_csv="data.csv", seed=0) -> rows`
- 网格：角度 `30–70°`（17 点）、后旋 `0–60 rad/s`（17 点）、每格 100 次抖动
  （σ 角度 1°、速率 0.1 m/s）

### validation.py
- CSV 格式：`shot_id, release_x, release_y, release_z, v0x, v0y, v0z, backspin, actual_outcome`
- `actual_outcome`：命中(具体子类) = `swish` / `rim-in` / `board-in`；命中(旧标签，仅二分类) = `bounce-in` / `made` / `in`；未中 = `miss` / `out` / `no`
- `predict(shot) -> (predicted_outcome, predicted_binary)`，`predicted_outcome` ∈ `swish` / `rim-in` / `board-in` / `miss`
- `run_validation(csv_path="dummy_data.csv")`：输出二分类指标（一致率 + Wilson 95% CI + precision/recall/specificity/F1/MCC + Cohen's kappa + 无信息率基线）与 4 类多分类混淆矩阵
- `wilson_ci(k, n, z=1.96)`：Wilson 二项置信区间（小样本误差量化）
- `make_dummy_data(csv_path="dummy_data.csv", n=20, seed=0, correlated=False)`

## 4. 当前成果（已跑通）

- **命中概率峰值**：罚球 `55°`、`45 rad/s`，`P ≈ 0.77`；三分球 `48°`、`48.8 rad/s`，`P ≈ 0.80`
  （后旋维度存在宽平台 ~15–45 rad/s，具体峰值随随机种子略有浮动）
- **轨迹偏差**：以真空仰角（约 55.7°）出手，真实（阻力+后旋）轨迹到达筐面时
  **偏低约 40.2 cm**；同样仰角/后旋下，**三分球（6.75 m）偏低约 117.4 cm**，
  比罚球多偏 77.2 cm（`plotting.py`，`free_vs_three_drag.png`）
- **单发样例**：7.5 m/s、51°、23 rad/s → `swish`（穿过筐面水平偏移 r=0.055 m）
- **验证链路**：dummy 随机标签下 Agreement ≈ 35%，Cohen's kappa ≈ −0.18
  （随机基线，无意义）；`make_dummy_data(correlated=True)` 自洽模式 ≈ 100%、
  kappa ≈ 1.0；20 发样本的一致率 Wilson 95% CI 约 [18%, 57%]，说明小样本下
  裸比例不确定度很大，须报告区间

## 5. To-Do（下一步）

- [ ] 导入真实 SportVU / 自拍 60 fps 数据，跑 `validation.py` 得到真实一致率 + 置信区间 + kappa
- [ ] 用文献速率标定三分球出手速度后重跑三分扫描，使罚球/三分峰值水平可直接比较
- [ ] 写最终报告（方法、结果、局限、伦理）
- [ ] （可选）调 `C_L0` 使最优后旋更接近计划书的 23 rad/s
- [ ] （可选）用 `pip freeze` 固定精确依赖版本
