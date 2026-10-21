# COMP1110 Project Plan (v2) — A Physics-Based Basketball Shot Simulation

> 这是 `Basketball-Free-Throw-Project-Plan-v2-3ce56a5a.md` 的改进版（2026-10-21），
> 原版（pypdf 兜底转换、行宽破碎、无标题层级）保留在同目录。
> 处理原则：只重排版式 + 补回 PDF 文本提取时丢失的撇号/标点，不增删内容事实；
> PDF（`Basketball-Free-Throw-Project-Plan-v2.pdf`）始终是可引用的原始来源。
> 姊妹变体 `-eaf0a7e2.md`（同一源 PDF 的另一次转换）在结局数量与文献清单上与此
> 不一致——两版差异与判定依据见文末附录；正文以本变体（四结局、Okubo & Hubbard）
> 与源 PDF 为准。

- **Title:** A Physics-Based Basketball Shot Simulation: Release Geometry, Backspin, and Ball Dynamics under Air Drag and Magnus Effects
- **Course:** COMP1110 Computing and Data Science in Everyday Life, 2026/27 Semester 1
- **Team members (5):**

| 成员 | 分工 |
|---|---|
| He Runlong | problem framing and literature |
| Li Zhenyi | projectile physics and integration |
| Shao Linjun | backboard / rim collision model |
| Liang Xuanshuo | dataset and validation |
| Chen Yin | visualisation and writing |

## 1. Title and Team Members

As above.

## 2. Problem Statement and Solution Concept

### 2.1 Motivation and Research Context

The prediction of basketball shooting outcomes has been studied by several researchers.
Notably, Cao et al. (2017) demonstrated that OpenPose can estimate release parameters
and predict shot outcomes, while Nakai et al. (2018) used it to analyse shooting
kinematics and provide posture correction feedback. These approaches focus on the
shooter's body mechanics rather than the physics of the ball in flight. Physics-based
models (Brancazio, 1981; Okubo and Hubbard, 2006) study idealised trajectories but
often neglect backspin effects or simplify rim/board collisions. Our project takes a
different angle: we focus on the ball's physics in flight — how release geometry,
backspin, air drag, and Magnus lift jointly determine shot outcomes. This complements
pose-estimation approaches by modelling what happens to the ball after release.

### 2.2 Problem Statement

A basketball in flight is a rigid-body problem: its trajectory is set by three release
parameters — release point, release force (initial velocity vector), and release
backspin — and shaped by gravity, air drag, and Magnus lift from spin. When the ball
meets the backboard or rim, the outcome depends on geometric collision with rigid
surfaces, with kinetic energy lost at each bounce.

**Research question:** Given a rigid, immovable backboard and rim with a fixed
restitution constant, can a pure-physics simulation driven by release point, release
force vector, and release backspin (with air drag and Magnus lift) reproduce whether
a shot (a) scores a swish, (b) bounces off the rim and goes in, (c) bounces off the
backboard and goes in, or (d) misses? How large is the model's disagreement with
real-world measured shots?

### 2.3 Scope

**In scope:**

- Three release parameters: release point `(x, y, z)`, release force vector
  `(v0x, v0y, v0z)`, initial backspin rate `(omega)`.
- Air drag (quadratic) and Magnus lift from backspin.
- Rigid, immovable backboard (vertical plane) and rigid, immovable rim (torus);
  inelastic collisions with a single restitution constant `e = 0.7`.
- Scoring rule: `swish`, `rim-and-in`, `board-and-in`, and `miss` outcomes.
- Extension: comparison of free-throw vs. 3-point shot dynamics, examining how
  release distance and launch angle alter the importance of air drag and Magnus
  effects.

**Out of scope:**

- Ball deformation, rim flexing, backboard vibration.
- Player physiology, fatigue, or psychological factors.
- Side-spin and wobble; we focus on backspin only.
- Machine-learning correction of physics equations — the model is pure physics.
- Real-time pose estimation or video analysis.

## 3. Computing and Data Science Connection

Main project type: algorithmic / simulation-modelling (pure physics), with a small
data-analysis component for model validation.

Key concepts and tools:

- **Numerical integration** (Python, numpy, RK4 or semi-implicit Euler) — core of the simulation.
- **Air drag and Magnus lift equations** — convert release parameters into continuous trajectories.
- **Rigid-body collision detection** — plane vs sphere (backboard), torus vs sphere (rim), with restitution constant `e`.
- **Outcome labelling** — `swish`, `rim-bounce-in`, `board-bounce-in`, and `miss` classification.
- **Parameter sweep** — grid search over release angle and backspin, producing a make-probability surface.
- **External dataset** (NBA SportVU / Kaggle / own 20–30 filmed free throws) — used only for validation, not training.
- **Error quantification** — reporting disagreement rate between predicted and recorded outcomes.

**Technical approaches:** We adopt a calculation-based (physics simulation) approach as
the core method, estimating physical parameters like air resistance and ball spin from
video footage using computer vision. An AI-based (data-driven) approach — requiring
many multi-angle shooting videos and ML models — is discussed as a potential extension
but deemed beyond feasible scope for this course project. The project is not
machine-learning based. Every prediction is the result of solving physics equations
with fixed constants.

## 4. Literature / Background Review

We will cover roughly 10–15 sources, organised into three thematic clusters.

### Cluster 1: Physics of basketball and ball dynamics

- Brancazio, P. J. (1981). Physics of basketball. *Am. J. Phys.*, 49(4), 356–365. — Classical projectile model with fixed restitution.
- Okubo, H., & Hubbard, M. (2006). Dynamics of the basketball shot with application to the free throw. *J. Sports Sci.*, 24(12), 1303–1314. — Validated ball-flight model with drag and backspin; closest template for our approach.
- Hamilton, G. R., & Reinschmidt, C. (1997). Optimal trajectory for the basketball free throw. *J. Sports Sci.*, 15(5), 491–504. — Optimal-trajectory model; baseline for validating our integrated trajectory.
- White, C. (2011). *Projectile dynamics in sport: principles and applications*. Routledge. — Reference for restitution and inelastic contact modelling.

### Cluster 2: Computer vision and pose estimation

- Cao, Z., et al. (2017). OpenPose: Realtime multi-person 2D pose estimation. arXiv:1611.08050. — Pose-estimation pipeline for works like Nakai et al. (2018).
- Nakai, M., Tsunoda, Y., Hayashi, H., & Murakoshi, H. (2018). Prediction of basketball free throw shooting by OpenPose. In *New Frontiers in Artificial Intelligence* (JSAI-isAI 2018), Springer. — Vision-based release parameter estimation; distinct from our ball-physics approach.

### Cluster 3: Kinematics and data sources

- Okazaki, V. H. A., Rodacki, A. L. F., & Satern, M. N. (2015). A review on the basketball jump shot. *Sports Biomech.*, 14(2), 190–205. — Empirical release parameter ranges.
- NBA SportVU / AWS public tracking datasets. — External validation data.
- Our own filmed dataset (20–30 free throws, mobile camera at 60 fps).
- Tran, C. M., & Silverberg, L. M. (2008). Optimal release conditions for the free throw in men's basketball. *J. Sports Sci.*, 26(11), 1147–1155. — Calibrating parameter sweep ranges.

**Research gap:** Most existing simulations either (a) ignore backspin and Magnus lift,
(b) do not separate swish from rim-bounce outcomes, or (c) treat the rim as flexible.
The OpenPose approach focuses on posture correction rather than ball physics. No recent
study combines (i) a single fixed restitution constant, (ii) rigid board and rim,
(iii) explicit swish vs. rim-bounce vs. board-bounce comparison, and (iv) a single
error number against external data. This benchmark is our contribution.

## 5. Feasibility, Limitations, and Ethics

**Feasibility:** The equations of motion (drag + Magnus + gravity) are well-established
and implementable in Python/numpy quickly. RK4 integration and sphere-plane/torus
collision detection are standard problems with reference implementations. A single
smartphone at 60 fps suffices for data collection. Parameter sweeps over a grid of
release conditions complete in minutes to hours on a standard laptop.

**Constants and data:** All physics constants (g, rho_air, C_d, S [spin/Magnus
parameter], ball mass, ball radius, restitution e, board/rim geometry) are hard-coded
as Python constants and frozen after initial derivation — not tuned to the dataset.
Validation uses NBA SportVU open data and 20–30 filmed free throws.

**Limitations we will explicitly state:**

- Rigid board and rim — real rims flex and boards vibrate; rim-bounce-in outcomes will be less accurate than swish outcomes.
- Single restitution constant `e` is a simplification; real board and rim contacts have different `e` values.
- Spin decay in air beyond Magnus force is not modelled; spin is held constant during flight.
- Small empirical sample — the error number is a sanity check, not a statistically strong claim.
- We will not claim the model predicts real-player performance — only that it is physically consistent under stated simplifications.

**Ethics:** All filmed participants are group members who give verbal consent. Footage
is used only to label shot outcomes; no identifying face data is required. Footage is
stored locally and deleted after the final report. NBA SportVU data is public and
anonymised.

## 6. Timeline and Team Roles

| 阶段 | 周次 | 内容与分工 |
|---|---|---|
| Phase 1 | Weeks 1–3 | Literature review and physics model design. He Runlong and Li Zhenyi derive equations of motion and set up numerical integration. Shao Linjun researches collision detection. Liang Xuanshuo sources SportVU data and sets up filming. Chen Yin begins introduction and literature review. |
| Phase 2 | Weeks 4–6 | Core simulation. Li Zhenyi implements RK4 integrator with drag and Magnus effects. Shao Linjun implements backboard and rim collision detection. He Runlong validates against Brancazio (1981). Liang Xuanshuo begins filming. Chen Yin drafts methods section. |
| Phase 3 | Weeks 7–9 | Extension and validation. Li Zhenyi extends simulation to 3-point shots. Liang Xuanshuo processes footage and extracts outcome labels. All members contribute to error analysis and validation. |
| Phase 4 | Weeks 10–12 | Integration, visualisation, and writing. Chen Yin coordinates final report and figure consistency. All members review and refine. Final submission and presentation. |

Roles may shift as the project progresses, but the named owners are the first point of contact for each milestone.

## 7. Expected Outcomes

- Working Python simulation predicting free-throw outcomes from release geometry and backspin.
- Make-probability heatmap showing success variation with release angle, height, and backspin.
- Quantitative validation against real-world dataset, reporting agreement rate.
- Comparative analysis of free-throw vs. 3-point shot physics.
- Preliminary feasibility assessment of an AI-based extension for future work.

---

## 附录 A · 本文件的来历与编辑说明

- 本文件由 `-3ce56a5a.md`（dsh-plugin-office-markdown 内置兜底转换器，2026-10-20，
  源 PDF 201,572 bytes，src 哈希 `3d0503032065e2d4`）重排而来：恢复标题层级、把
  PDF 换行破碎的段落合并成完整句、把 `•` 伪列表转成真列表、补回被 pypdf 剥离的
  所有格撇号与连接号。未增删任何内容句；"consts"→"constants" 为原文笔误修正。
- PDF 中的图片、表格结构与扫描内容从未进入任何转换版（`转换提示` 在原版尾部，
  本附录保留该结论）；如需精确引用，请引用源 PDF。

## 附录 B · 与姊妹变体 `-eaf0a7e2.md` 的差异（同一源 PDF）

| 位置 | 本变体（3ce56a5a） | `-eaf0a7e2` 变体 |
|---|---|---|
| §2.1 引用 | Nakai et al. (2018) + Okubo & Hubbard (2006) | Chen et al. (2020) + Alaways & Hubbard (2002) |
| §2.2 研究问题 | 四结局 (a) swish / (b) rim 弹进 / (c) board 弹进 / (d) miss | 仅三结局（漏掉 rim-and-in） |
| Cluster 1–3 文献 | Brancazio/Okubo&Hubbard/Hamilton/White + Cao/Nakai + Okazaki/SportVU/自拍/Tran&Silverberg | Brancazio/Alaways&Hubbard/Nürnberg/Hunt + Cao/Chen + Okazaki/SportVU/自拍/Wiley |

判定依据：项目当前实现与 `Report_Draft`、`Specifications.md` 引用的都是四结局、
Nakai/Okubo & Hubbard 一系——与 3ce56a5a 一致；eaf0a7e2 的三结局表述与其余文档矛盾，
且其替代文献无法与实现互证。引用计划书内容时以 **3ce56a5a（及源 PDF）** 为准，
eaf0a7e2 仅作对照存档。两份原版文件均保留。
