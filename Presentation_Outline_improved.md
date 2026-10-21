# Presentation Outline — Basketball Shot Simulation (8–10 slides)

> 这是 `Presentation_Outline.md` 的改进版（2026-10-21），原版文件保留在同目录。
> 主要变更：Slide 8/10 更新到当前真实状态（自洽验证一条命令、`data_validation/`
> 已暂存的 SportVU 轨迹与 `valid_data.csv` 的假设来源提示）、Slide 10 交付清单补全
> （exe、HTML 浏览器、GIF 演示、2D 扫描、自检链），并给每页加时间预算。

> 期末汇报 PPT 大纲。每页给出「放哪张图」和「演讲者要点」。8–10 页按 10 分钟演讲
> 设计，每页约 60 s；Slide 8 的验证仍在进行中，按"in progress"处理。

---

## Slide 1 — Title  (~1 min)

**内容**：项目标题、组员姓名、课程（COMP1110, 2026/27 S1）。

**图**：无（可放一张篮球/轨迹的示意封面图；`trajectory_comparison.png` 做背景也可）。

**演讲**：
- "Our project is a pure-physics basketball shot simulation."
- 一句话点题：给定出手点、出手速度、后旋，预测这球是 swish、rim-in、board-in，还是 miss。

---

## Slide 2 — Motivation: Why Ball Physics, Not Pose Estimation  (~1 min)

**图**：无需新图；可用一张「两个方向」的对比图（姿态估计 vs 物理建模），或直接列文献。

**演讲**：
- 已有工作分两类：OpenPose 姿态纠正（Cao 2017, Nakai et al. 2018）只关注投手身体；经典弹道模型（Brancazio 1981, Okubo & Hubbard 2006）常忽略后旋或简化碰撞。
- "没有一项研究同时把出手几何、自旋气动力、刚性碰撞三者做全 —— 这就是我们的缺口。"

---

## Slide 3 — Research Question & Scope  (~1 min)

**图**：无；或画一个简单的「三力 + 两碰撞」示意图（x=0 竖直板 + y=3.05 圆环即可）。

**演讲**：
- 研究问题："一块刚性篮板 + 一个刚性篮筐 + 单一恢复系数 e = 0.7，能否复现 swish、rim-in、board-in、miss 四种结局？"
- 只建模三个力：重力、二次空气阻力（∝ v²）、马格努斯升力（后旋）。
- 范围外：球形变、篮筐弹性、篮板振动、侧旋、ML 修正、实时姿态估计。

---

## Slide 4 — Methods: The Physics & RK4  (~1.5 min)

**图**：写三个力的公式 + 状态向量 + RK4 递推式（用公式排版）。

**演讲**：
- 三个力：F_g = (0, −mg, 0)；F_d = −½ρC_dA|v|v；F_M = ½ρA·C_L0·R·(ω × v)。
- 后旋方向 ω = (0, 0, +ω) 产生升力。
- 用四阶 Runge–Kutta（NumPy）积分 6 维状态 [x, y, z, vx, vy, vz]；dt = 1 ms。
- 一句带过：每个扫描结果行都带配置元数据（种子、名义速度、抖动 σ），可逐行追溯。

---

## Slide 5 — Methods: Rigid Collisions  (~1.5 min)

**图**：画篮板（竖直平面 x = 0）与篮筐（圆环 y = 3.05, 半径 0.225 m）的几何示意。

**演讲**：
- 篮板：平面–球碰撞（最近点法，支持边/角）；篮筐：圆环–球碰撞（球心到圆环最近点距离 ≤ 球半径）。
- 反弹只改法向分量：v' = v − (1 + e)(v · n)n，e = 0.7；默认切向保留比例 1.0（无摩擦，切向不变）。
- 同一位置可能同时检测到板与筐两个接触：`resolve_contacts` 有限轮顺序处理，弹性只第一轮施加、后续轮只消向内速度（防虚增能量），重叠无法全消时显式保留而不是抖动。
- 得分判据：球心向下穿过 y = 3.05 且水平距筐心 ≤ 0.105 m；按碰撞历史细分四种结局 —— 没碰 = `swish`、只碰筐 = `rim-in`、碰过篮板 = `board-in`、否则未进 = `miss`。

---

## Slide 6 — Results: Make-Probability Surface  (~1.5 min)

**图**：`make_probability.png`（罚球）、`make_probability_three.png`（三分球），或并排 `make_probability_comparison.png`；可加 `outcome_breakdown.png` 的缩略。

**演讲**：
- 扫描：角度 30–70° × 后旋 0–60 rad/s，每格 100 次抖动投篮（σ 角度 1°、速率 0.1 m/s）。
- 罚球峰值 **P ≈ 0.77，约 55°、45 rad/s**；三分球（6.75 m、9.5 m/s，角度网格 36–60°）峰值 **P ≈ 0.80，约 48°、49 rad/s**（图中峰值附近有星号标记）。
- 关键结论：最优角度下移约 7°（55° → 48°），后旋仍然要强（≈45–49 rad/s）。
- 诚实提示（一句）：两套扫描名义速度不同（7.5 vs 9.5 m/s），0.77 与 0.80 不是同难度对比——可比的是"角度下移 + 阻力偏差随距离增大"这两条趋势。

---

## Slide 7 — Results: Vacuum Aim vs. Real Flight (Free Throw vs Three)  (~1 min)

**图**：`free_vs_three_drag.png`（罚球 vs 三分球的真空/真实轨迹 + 偏差柱状图）；备选 `trajectory_comparison.png` / `trajectory_comparison_three.png`。

**演讲**：
- 如果"当作真空"瞄准筐心，真实（有阻力 + 后旋）飞行到达筐面时，**罚球偏低约 40.2 cm，三分球（6.75 m）偏低约 117 cm**，多偏 77 cm。
- 说明阻力与马格努斯力不可忽略，且**距离越远越重要** —— 这是计划书"罚球 vs 三分球"扩展的核心结论。

---

## Slide 8 — Validation (In Progress)  (~1.5 min)

**图**：暂无最终图；可放验证流程框图（data_prep / extract → shot-level CSV → validation.py），或标注「data import in progress」。

**演讲**：
- 验证设计：20–30 个组员罚球 60fps 逐帧追踪 + 公开 NBA SportVU，记录出手几何与真实结局。
- 报告的不止是单一偏差率：还给出 **Wilson 95% 置信区间**（小样本下必须有区间）+ **Cohen's kappa**（相对偶然一致）+ **四种结局的混淆矩阵与每类 F1**。
- 举例：随机占位标签下一致率 35%、kappa ≈ −0.18（不比猜好）；20 发的 35% 其 95% 区间约 [18%, 57%] —— 直观说明"一个裸数字不够"。
- 演示一条命令：`python validation.py --make-dummy --correlated` 再 `python validation.py`（或直接 `python validation.py selfcheck`）→ 自洽 100%、kappa≈1，证明链路正确。
- **诚实说明：真实数据验证尚未完成**。当前 `data_validation/` 已有 SportVU 风格轨迹抽取（24,073 帧，但时间戳精度在导出时被压平、坐标轴约定未确认）与 5 条出手初值（单位/轴未记录）；`valid_data.csv`（305 行，可被 `validation.py` 直接读取）的出手参数由 `data_prep.py` 按显式假设合成（直线距离 → x = −0.375 − d、固定 51° 真空解速度、统一 23 rad/s 后旋、缺省出手高度 2.0 m），因此它验证的是"假设 + 二元标签"，还不是实测——最终数字待补。

---

## Slide 9 — Limitations & Ethics  (~1 min)

**图**：无；列两栏（局限 / 伦理）。

**演讲**：
- 局限：刚性筐/板、单一 e = 0.7、后旋恒定不衰减、球形变和篮板振动忽略、样本小。
- 一句补充（选讲）：仓库里另有一套常数不同的 2D 演示模型（0.60 kg / ρ1.204 / C_d 0.47 / 固定 C_L 0.20 / 切向 0.85），只做教学可视化，其数值结论与本报告分开标注。
- 伦理：拍摄对象是组员、口头同意、视频本地保存、只标结局不标人脸、报告后删除视频；SportVU 数据公开匿名。

---

## Slide 10 — Deliverables & Next Steps  (~1 min)

**图**：可放项目文件结构图或两张结果图缩略；也可现场 30 s 双击 `basketball_shot_2d.exe` 演示。

**演讲**：
- 已交付：可运行的 Python 模拟（RK4 + 碰撞 + 多接触有限轮）、命中概率热力图、结局占比分解图（`outcome_breakdown.png`）、真空 vs 真实轨迹对比、验证框架（Wilson CI / kappa / MCC / 混淆矩阵）、交互式 HTML 轨迹浏览器（`basketball_interactive.html`，浏览器双击即开）、免安装 exe、6 个演示 GIF、2D 必中速度窗口扫描数据。
- 可复现性：三套 unittest + 各脚本 `--check` / `--selfcheck` 全绿，改代码后可一键回归。
- 下一步：给真实数据补齐出手参数/backspin/标签完成验证、用文献速度标定三分扫描、写最终报告。
- 一句收尾："A pure-physics model, no training, three forces, two rigid surfaces — and one number: the disagreement rate."
