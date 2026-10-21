# Presentation Outline — Basketball Shot Simulation (8–10 slides)

> 期末汇报 PPT 大纲。每页给出「放哪张图」和「演讲者要点」。10 页按约 10 分钟演讲
> 设计，每页约 60 s。仿真扫描已运行；Slide 8 的经验验证仍未完成。

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
- 扫描：罚球角度 30–70°、三分角度 36–60°，后旋 0–60 rad/s；两组均为 17 × 17 格、每格 100 次抖动投篮（σ 角度 1°、速率 0.1 m/s）。
- 罚球峰值 **P = 0.77，55°、45 rad/s**，由 swish 0.52、rim-in 0.15、board-in 0.10 构成。
- 三分球（6.75 m、9.5 m/s）峰值 **P = 0.79，45°、37.5 rad/s**；该峰值格全部为 board-in。
- 本次扫描峰值参数的角度相差 10°、后旋相差 7.5 rad/s。两套名义速度不同（7.5 vs 9.5 m/s），命中率不可作为同难度比较；图中星号标示各自峰值。

---

## Slide 7 — Results: Vacuum Aim vs. Real Flight (Free Throw vs Three)  (~1 min)

**图**：`free_vs_three_drag.png`（罚球 vs 三分球的真空/真实轨迹 + 偏差柱状图）；备选 `trajectory_comparison.png` / `trajectory_comparison_three.png`。

**演讲**：
- 如果"当作真空"瞄准筐心，真实（有阻力 + 后旋）飞行到达筐面时，**罚球偏低 40.2 cm，三分球（6.75 m）偏低 117.4 cm**，多偏 77.2 cm。
- 说明阻力与马格努斯力不可忽略，且**距离越远越重要** —— 这是计划书"罚球 vs 三分球"扩展的核心结论。

---

## Slide 8 — Validation Pipeline (Empirical Validation Pending)  (~1.5 min)

**图**：验证流程框图（data_prep / extract → shot-level CSV → validation.py），并标注「synthetic inputs; empirical validation pending」。

**演讲**：
- 验证实现已报告一致率、**Wilson 95% CI**、Cohen's kappa、MCC、precision/recall/F1 与四类混淆矩阵。
- 当前数据分为 300 行的 `valid_data_2D.csv`（直线近似，使用 source speed/angle）和 35 行的 `valid_data_3D.csv`（暂定 3D 输入）。前者为 **153/300 一致（51.00%；Wilson 95% CI [45.37%, 56.61%]）**，后者为 **0/35 一致（0.00%；Wilson 95% CI [0.00%, 9.89%]）**；两份输入均包含未验证的假设，不能作为经验准确率。
- 所以该数值不是经验准确率；它反映的是当前合成假设及标签。SportVU 导出仍需恢复时间精度并核实坐标系，出手速度、后旋、样本关联和真实结局也尚未齐全。
- 自洽占位数据的 20/20、100% agreement（κ = 1）只证明验证代码链路能运行，不能证明模型准确。

---

## Slide 9 — Limitations & Ethics  (~1 min)

**图**：无；列两栏（局限 / 伦理）。

**演讲**：
- 局限：刚性筐/板、单一 e = 0.7、后旋恒定不衰减、球形变和篮板振动忽略；当前没有可用于经验验证的实测 shot-level 输入。
- 一句补充（选讲）：仓库里另有一套常数不同的 2D 演示模型（0.60 kg / ρ1.204 / C_d 0.47 / 固定 C_L 0.20 / 切向 0.85），只做教学可视化，其数值结论与本报告分开标注。
- 伦理：拍摄对象是组员、口头同意、视频本地保存、只标结局不标人脸、报告后删除视频；SportVU 数据公开匿名。

---

## Slide 10 — Deliverables & Next Steps  (~1 min)

**图**：可放项目文件结构图或两张结果图缩略；也可现场演示 2D 交互式模拟器。

**演讲**：
- 已交付：RK4 与多接触碰撞模拟、3D 罚球/三分扫描与七张图、真空与真实轨迹对比、验证框架、交互式 HTML、2D 程序与演示 GIF。
- 独立的 2D 冻结常数扫描也已完成：最宽速度窗口为罚球 0.30 m/s（47.5° / 35 rad/s）和三分 0.24 m/s（52.5° / 5 rad/s）；不要与 3D 命中概率混为一谈。
- 本次运行检查通过：核心测试 13/13、碰撞测试 24/24、扫描测试 2/2、2D 场景 6/6、实验复现 3/3、绘图 7/7、验证自检通过。
- 下一步：确认 tracking 数据来源、坐标/单位/时间戳，采集或恢复逐球的释放状态、后旋和真实结局；随后才报告实测验证，并在可比速度下重跑三分扫描。
- 一句收尾："A reproducible physics model is in place; empirical agreement still needs measured shot data."
