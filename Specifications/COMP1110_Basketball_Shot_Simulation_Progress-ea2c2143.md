<!-- dsh-office-markdown converter=builtin fidelity=limited at=2026-10-21T04:52:51.158Z srcbytes=652428 srchash=b6ddd3dce585a0c7 -->
<!-- 由 dsh-plugin-office-markdown 内置兜底转换器生成（非 MarkItDown），版式/图表/批注/图片等信息可能缺失，保真度有限。 -->
> 源文件：`COMP1110_Basketball_Shot_Simulation_Progress.pptx`
> 转换器：内置兜底（fallback.py）

## 幻灯片 1：A Physics-Based Basketball Shot Simulation

COMP1110 Computing and Data Science in Everyday Life, 2026/27 Semester 1
Progress report, week 6. He Runlong, Li Zhenyi, Shao Linjun, Liang Xuanshuo, Chen Yin

## 幻灯片 2：Project at a Glance

Three release numbers drive everything: point (x, y, z), velocity vector, backspin rate.
Gravity, quadratic air drag and Magnus lift shape the flight; the rigid board and rim decide every bounce.
Pure physics, no training.

## 幻灯片 3：Why Ball Physics, Not Pose Estimation

OpenPose work (Cao 2017, Chen 2020) corrects the shooter's posture.
Classical models (Brancazio 1981, Alaways and Hubbard 2002) drop backspin or fuse the bounce outcomes.
No study fills all five columns. That gap is our benchmark.

## 幻灯片 4：Model Concept and Research Question

Can a simulation with a rigid board, rigid rim and one restitution constant e = 0.7 reproduce swish, board-and-in and miss?
Weight, v-squared drag and spin-driven Magnus lift are the only forces modelled.

## 幻灯片 5：Method and Tools

RK4 integration in Python and numpy.
Plane-sphere and circle-pair contacts, four labelled outcomes, then a sweep over angle and spin.
SportVU plus our own filmed throws supply labels only; every constant stays frozen.

## 幻灯片 6：Scope Boundaries

Release point, velocity vector, backspin
Quadratic air drag + Magnus lift
Rigid vertical board plane
Rigid rim, inelastic contact e = 0.7
Swish, rim-in, board-in, miss
Free-throw versus 3-point extension

Ball deformation, rim flex, board vibration
Player fatigue and psychology
Side-spin and wobble
Machine-learning correction of the physics
Real-time pose estimation
Claims about real players' performance

## 幻灯片 7：Early Result: Make-Probability Surface

Grid sweep: 17 angles x 17 spin rates, 200 jittered shots per cell.
Peak P(make) = 0.86 near 51 degrees with 23 rad/s of backspin, split into 0.67 swish and 0.14 bounce-in.
Mean P climbs from 0.61 without spin to 0.69 at the top of the range.

## 幻灯片 8：Extension: Free Throw versus 3-Point

Air costs roughly 4 per cent more launch speed at both distances.
Aim as if in a vacuum and the ball reaches the rim plane low: 34 cm on a free throw, 82 cm from three-point range.
Drag and spin matter more the farther the shot.

## 幻灯片 9：Validation Design

20 to 30 group-member free throws filmed at 60 fps, plus public NBA SportVU tracking.
Frame by frame tracking gives release geometry and the recorded outcome class.
We report a single disagreement rate, as a sanity check rather than a statistical claim.

## 幻灯片 10：Timeline and Current Progress

Phase 1, literature review and model design, is complete.
Phase 2, the RK4 integrator and the collision code, is in progress this week.
Extension and footage labels follow in weeks 7 to 9; writing and figures in weeks 10 to 12.

## 幻灯片 11：Stated Limitations and Ethics

Real rims flex, real boards vibrate
One restitution constant for two contacts
Spin held constant, no decay in flight
Bounce-in outcomes less accurate than swish
Small empirical sample

Filmed participants are team members
Verbal consent, footage stays local
Outcomes labelled, no face data needed
Video deleted after the final report
SportVU data is public and anonymised

## 幻灯片 12：Deliverables and Next Steps

Working Python simulation of free-throw outcomes
Make-probability map over release angle and backspin
Disagreement rate against SportVU and our own footage
Free-throw versus 3-point comparison
Written note on an AI-based extension, kept out of scope
Next: finish the collision code, film 20 to 30 throws, widen the sweep