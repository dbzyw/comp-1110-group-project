# COMP1110 Basketball Shot Simulation — Progress Report (Week 6)

> 源文件：`COMP1110_Basketball_Shot_Simulation_Progress.pptx`（同目录有 `.pptx.bak`）。
> 转换器：内置兜底（fallback.py），版式/图表/图片信息可能缺失。

## Slide 1 — A Physics-Based Basketball Shot Simulation

- COMP1110 Computing and Data Science in Everyday Life, 2026/27 Semester 1.
- Progress report, week 6.
- He Runlong, Li Zhenyi, Shao Linjun, Liang Xuanshuo, Chen Yin.

## Slide 2 — Project at a Glance

- Three release numbers drive everything: point (x, y, z), velocity vector, backspin rate.
- Gravity, quadratic air drag and Magnus lift shape the flight; the rigid board and rim decide every bounce.
- Pure physics, no training.

## Slide 3 — Why Ball Physics, Not Pose Estimation

- OpenPose work (Cao 2017, Chen 2020) corrects the shooter's posture.
- Classical models (Brancazio 1981, Alaways and Hubbard 2002) drop backspin or fuse the bounce outcomes.
- No study fills all five columns. That gap is our benchmark.

## Slide 4 — Model Concept and Research Question

- Can a simulation with a rigid board, rigid rim and one restitution constant e = 0.7 reproduce swish, board-and-in and miss?
- Weight, v-squared drag and spin-driven Magnus lift are the only forces modelled.

*（此页只列三结局，Slide 6 却列四结局——疑为兜底转换丢字或讲稿本身两说法并存，原样保留；项目正式口径见 `Specifications.md` 的四结局。）*

## Slide 5 — Method and Tools

- RK4 integration in Python and numpy.
- Plane-sphere and circle-pair contacts, four labelled outcomes, then a sweep over angle and spin.
- SportVU plus our own filmed throws supply labels only; every constant stays frozen.

## Slide 6 — Scope Boundaries

| 纳入（In） | 排除（Out） |
|---|---|
| Release point, velocity vector, backspin | Ball deformation, rim flex, board vibration |
| Quadratic air drag + Magnus lift | Player fatigue and psychology |
| Rigid vertical board plane | Side-spin and wobble |
| Rigid rim, inelastic contact e = 0.7 | Machine-learning correction of the physics |
| Swish, rim-in, board-in, miss | Real-time pose estimation |
| Free-throw versus 3-point extension | Claims about real players' performance |

## Slide 7 — Early Result: Make-Probability Surface

- Grid sweep: 17 angles × 17 spin rates, 200 jittered shots per cell.
- Peak P(make) = 0.86 near 51 degrees with 23 rad/s of backspin, split into 0.67 swish and 0.14 bounce-in.
- Mean P climbs from 0.61 without spin to 0.69 at the top of the range.

## Slide 8 — Extension: Free Throw versus 3-Point

- Air costs roughly 4 per cent more launch speed at both distances.
- Aim as if in a vacuum and the ball reaches the rim plane low: 34 cm on a free throw, 82 cm from three-point range.
- Drag and spin matter more the farther the shot.

## Slide 9 — Validation Design

- 20 to 30 group-member free throws filmed at 60 fps, plus public NBA SportVU tracking.
- Frame by frame tracking gives release geometry and the recorded outcome class.
- We report a single disagreement rate, as a sanity check rather than a statistical claim.

## Slide 10 — Timeline and Current Progress

- Phase 1, literature review and model design, is complete.
- Phase 2, the RK4 integrator and the collision code, is in progress this week.
- Extension and footage labels follow in weeks 7 to 9; writing and figures in weeks 10 to 12.

## Slide 11 — Stated Limitations and Ethics

| 局限（Limitations） | 伦理（Ethics） |
|---|---|
| Real rims flex, real boards vibrate | Filmed participants are team members |
| One restitution constant for two contacts | Verbal consent, footage stays local |
| Spin held constant, no decay in flight | Outcomes labelled, no face data needed |
| Bounce-in outcomes less accurate than swish | Video deleted after the final report |
| Small empirical sample | SportVU data is public and anonymised |

## Slide 12 — Deliverables and Next Steps

- Working Python simulation of free-throw outcomes.
- Make-probability map over release angle and backspin.
- Disagreement rate against SportVU and our own footage.
- Free-throw versus 3-point comparison.
- Written note on an AI-based extension, kept out of scope.
- Next: finish the collision code, film 20 to 30 throws, widen the sweep.

---

## 附录 · 第 6 周快照 vs 仓库当前（2026-10-21）

本文件是第 6 周的状态快照，当时部分数字/说法已过时。现在读这份 deck 时，以下对照表
给出处置（**快照原文一律保留在上方各页**，本表只做阅读指引，不回改历史内容）：

| 快照说法 | 当前状态（3D 主流程） |
|---|---|
| 每格 200 抖动投篮（Slide 7） | `JITTER_SHOTS = 100`（`experiment.py`，每格 100 发） |
| 峰值 P=0.86 @ 51°、23 rad/s，拆 0.67 swish / 0.14 bounce-in（Slide 7） | 全网格峰值 P≈0.77 @ ≈55°、45 rad/s（星号标记在 `make_probability.png`；51°/23 是 UI/演示预设的单发基准场景，`--check` 6/6 复现） |
| 真空瞄准偏差 34 cm / 82 cm（Slide 8） | 40.2 cm（罚球）与 117.4 cm（三分 6.75 m），`free_vs_three_drag.png` |
| 只报告"单一不一致率"（Slide 9/12） | 已实现：一致率 + **Wilson 95% CI** + kappa + 无信息率基线 + precision/recall/specificity/F1/MCC + 4 类混淆矩阵（`validation.py`） |
| Phase 2 "进行中"，碰撞代码未完（Slide 10/12） | 碰撞层已交付：最近点边/角检测、批量、`detect_all`/多接触有限轮、位置校正（`../Collision.md` / `../collision.py`），且有 `../test_collision.py` |
| "swish, board-and-in and miss"（Slide 4） | 正式四结局 `swish / rim-in / board-in / miss`（Slide 6 与 `Specifications.md` 一致） |
| Slide 3/7 的文献（Chen 2020 / Alaways & Hubbard 2002） | `../Report_Draft.md` 引用 Nakai 2018 / Okubo & Hubbard 2006 / Tran & Silverberg 2008 等；与计划书变体差异见两版 plan 的附录 B |
| 验证数据"尚待拍摄" | `data_validation/` 已暂存 SportVU 风格轨迹（24,073 帧，精度/轴待修）+ 5 条初值 + 原始数据集 300 行 + `data_prep.py` 与 `valid_data.csv`（305 行，**参数为显式假设合成，非实测**；真实验证仍未完成） |
