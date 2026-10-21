<!-- dsh-office-markdown converter=builtin fidelity=limited at=2026-10-21T04:52:51.158Z srcbytes=652428 srchash=b6ddd3dce585a0c7 -->
<!-- 由 dsh-plugin-office-markdown 内置兜底转换器生成（非 MarkItDown），版式/图表/批注/图片等信息可能缺失，保真度有限。 -->
> 源文件：`COMP1110_Basketball_Shot_Simulation_Progress.pptx`
> 转换器：内置兜底（fallback.py）
> 以下进度与结果按 2026-10-21 的运行结果更新；历史 PPTX 快照可能保留旧数值。

## 幻灯片 1：A Physics-Based Basketball Shot Simulation

COMP1110 Computing and Data Science in Everyday Life, 2026/27 Semester 1
Progress update, 21 October 2026. He Runlong, Li Zhenyi, Shao Linjun, Liang Xuanshuo, Chen Yin

## 幻灯片 2：Project at a Glance

Three release numbers drive everything: point (x, y, z), velocity vector, backspin rate.
Gravity, quadratic air drag and Magnus lift shape the flight; the rigid board and rim decide every bounce.
Pure physics, no training.

## 幻灯片 3：Why Ball Physics, Not Pose Estimation

OpenPose work (Cao 2017, Chen 2020) corrects the shooter's posture.
Classical models (Brancazio 1981, Alaways and Hubbard 2002) drop backspin or fuse the bounce outcomes.
No study fills all five columns. That gap is our benchmark.

## 幻灯片 4：Model Concept and Research Question

Can a simulation with a rigid board, rigid rim and one restitution constant e = 0.7 reproduce swish, rim-in, board-in and miss?
Weight, v-squared drag and spin-driven Magnus lift are the only forces modelled.

## 幻灯片 5：Method and Tools

RK4 integration in Python and numpy.
Plane-sphere and circle-pair contacts, four labelled outcomes, then a sweep over angle and spin.
Constants remain frozen during evaluation. Current shot-level validation inputs are assumption-based; empirical validation against SportVU or filmed shots is not complete.

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

Executed sweep: 17 x 17 parameter cells, 100 jittered shots per cell (angle sigma = 1 degree; speed sigma = 0.1 m/s).
Free-throw peak P(make) = 0.77 at 55 degrees and 45 rad/s: 0.52 swish, 0.15 rim-in, and 0.10 board-in.
Three-point peak P(make) = 0.79 at 45 degrees and 37.5 rad/s; this peak cell is entirely board-in.
The sweeps use different nominal speeds (7.5 and 9.5 m/s), so peak probabilities are not a like-for-like difficulty comparison.

## 幻灯片 8：Extension: Free Throw versus 3-Point

Vacuum aim versus flight with drag and backspin: the ball reaches the rim plane 40.2 cm low on a free throw and 117.4 cm low from three-point range (6.75 m).
Drag and spin matter more the farther the shot.

## 幻灯片 9：Validation Design

The pipeline reports agreement, Wilson 95% CI, Cohen's kappa, binary metrics, and a four-class confusion matrix.
The current 305-row valid_data.csv run gives 152/305 agreement (49.8%; Wilson 95% CI [44.3%, 55.4%]), kappa = 0.000, and a 50.2% majority-class baseline.
This is not an empirical score: physical inputs are assumption-generated, labels are binary, and five appended initial conditions have unverified axes/units and assigned outcomes. The model predicted every row as a miss.
Self-consistent dummy data gives 20/20 agreement (100%, kappa = 1.000), which checks the pipeline only.
Real validation still requires measured release states, backspin, verified coordinate/time conventions, and observed shot outcomes.

## 幻灯片 10：Timeline and Current Progress

RK4 flight integration, rigid-contact collision handling, and the 3D/2D simulation paths are implemented.
All four parameter sweeps and seven result figures have been generated; the six documented 2D demo scenarios reproduce successfully.
Empirical validation remains pending because shot-level physical inputs and tracking conventions are not verified.

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

Working Python simulation, reproducible parameter sweeps, make-probability plots, outcome breakdown, and vacuum-versus-flight comparisons
Separate 2D velocity-window scans: widest windows are 0.30 m/s for free throw (47.5 degrees, 35 rad/s) and 0.24 m/s for three-point (52.5 degrees, 5 rad/s); these use separate frozen constants
Automated checks passed: core 13/13, collision 24/24, experiment 2/2, 2D scenarios 6/6, experiment self-check 3/3, plot self-check 7/7, and validation self-check
Written note on an AI-based extension, kept out of scope
Next: verify data units, axes, timestamps, and shot linkage; obtain measured release position/velocity, backspin, and outcome labels; then complete empirical validation and calibrate the three-point speed