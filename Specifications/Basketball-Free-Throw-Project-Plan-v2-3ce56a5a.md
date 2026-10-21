<!-- dsh-office-markdown converter=builtin fidelity=limited at=2026-10-20T16:50:08.737Z srcbytes=201572 srchash=3d0503032065e2d4 -->
<!-- 由 dsh-plugin-office-markdown 内置兜底转换器生成（非 MarkItDown），版式/图表/批注/图片等信息可能缺失，保真度有限。 -->
> 源文件：`Basketball-Free-Throw-Project-Plan-v2.pdf`
> 转换器：内置兜底（fallback.py）

COMP1110 Project Plan 
A Physics-Based Basketball Shot Simulation: Release Geometry, Backspin, and Ball 
Dynamics under Air Drag and Magnus Effects 
 
 
1. Title and Team Members 
Title: A Physics-Based Basketball Shot Simulation: Release Geometry, Backspin, and Ball 
Dynamics under Air Drag and Magnus Effects. 
Team members (5): He Runlong (problem framing and literature), Li Zhenyi (projectile 
physics and integration), Shao Linjun (backboard / rim collision model), Liang Xuanshuo 
(dataset and validation), Chen Yin (visualisation and writing). 
Course: COMP1110 Computing and Data Science in Everyday Life, 2026/27 Semester 1. 
2. Problem Statement and Solution Concept 
2.1 Motivation and Research Context 
The prediction of basketball shooting outcomes has been studied by several researchers. 
Notably, Cao et al. (2017) demonstrated that OpenPose can estimate release parameters 
and predict shot outcomes, while Chen et al. (2020) used it to analyse shooting kinematics 
and provide posture correction feedback. These approaches focus on the shooters body 
mechanics rather than the physics of the ball in flight. Physics-based models (Brancazio, 
1981; Alaways and Hubbard, 2002) study idealised trajectories but often neglect backspin 
effects or simplify rim/board collisions. Our project takes a different angle: we focus on the 
balls physics in flight - how release geometry, backspin, air drag, and Magnus lift jointly 
determine shot outcomes. This complements pose-estimation approaches by modelling 
what happens to the ball after release. 
2.2 Problem Statement 
A basketball in flight is a rigid-body problem: its trajectory is set by three release 
parameters - release point, release force (initial velocity vector), and release backspin - and 
shaped by gravity, air drag, and Magnus lift from spin. When the ball meets the backboard 
or rim, the outcome depends on geometric collision with rigid surfaces, with kinetic energy 
lost at each bounce. 
Research question: Given a rigid, immovable backboard and rim with a fixed restitution 
constant, can a pure-physics simulation driven by release point, release force vector, and 

release backspin (with air drag and Magnus lift) reproduce whether a shot (a) scores a 
swish, (b) bounces off the backboard and goes in, or (c) misses? How large is the models 
disagreement with real-world measured shots? 
2.3 Scope 
In scope: 
• Three release parameters: release point (x, y, z), release force vector (v0x, v0y, v0z), 
initial backspin rate (omega). 
• Air drag (quadratic) and Magnus lift from backspin. 
• Rigid, immovable backboard (vertical plane) and rigid, immovable rim (torus); inelastic 
collisions with a single restitution constant e = 0.7. 
• Scoring rule: swish, rim-and-in, board-and-in, and miss outcomes. 
• Extension: comparison of free-throw vs. 3-point shot dynamics, examining how release 
distance and launch angle alter the importance of air drag and Magnus effects. 
Out of scope: 
• Ball deformation, rim flexing, backboard vibration. 
• Player physiology, fatigue, or psychological factors. 
• Side-spin and wobble; we focus on backspin only. 
• Machine-learning correction of physics equations - the model is pure physics. 
• Real-time pose estimation or video analysis. 
3. Computing and Data Science Connection 
Main project type: algorithmic / simulation-modelling (pure physics), with a small data-
analysis component for model validation. 
Key concepts and tools: 
• Numerical integration (Python, numpy, RK4 or semi-implicit Euler) - core of the 
simulation. 
• Air drag and Magnus lift equations - convert release parameters into continuous 
trajectories. 
• Rigid-body collision detection - plane vs sphere (backboard), torus vs sphere (rim), with 
restitution constant e. 
• Outcome labelling - swish, rim-bounce-in, board-bounce-in, and miss classification. 
• Parameter sweep - grid search over release angle and backspin, producing a make-
probability surface. 
• External dataset (NBA SportVU / Kaggle / own 20-30 filmed free throws) - used only for 
validation, not training. 
• Error quantification - reporting disagreement rate between predicted and recorded 
outcomes. 

Technical approaches: We adopt a calculation-based (physics simulation) approach as the 
core method, estimating physical parameters like air resistance and ball spin from video 
footage using computer vision. An AI-based (data-driven) approach - requiring many multi-
angle shooting videos and ML models - is discussed as a potential extension but deemed 
beyond feasible scope for this course project. 
The project is not machine-learning based. Every prediction is the result of solving physics 
equations with fixed constants. 
4. Literature / Background Review 
We will cover roughly 10-15 sources, organised into three thematic clusters: 
Cluster 1: Physics of basketball and ball dynamics. 
• Brancazio, P. J. (1981). Physics of basketball. Am. J. Phys., 49(4), 356-365. - Classical 
projectile model with fixed restitution. 
• Alaways, L. W., & Hubbard, M. (2002). Flight dynamics of the basketball. Sports Eng., 
5(1), 29-37. - Drag and Magnus lift coefficients for a spinning basketball. 
• Nürnberg, S., et al. (2021). A validated simulation model of basketball free-throw 
trajectories. Sports Eng., 24, 1-12. - Template for error quantification. 
• Hunt, J. C. (2011). Projectile dynamics in sport. Human Kinetics. - Reference for 
restitution and inelastic contact modelling. 
Cluster 2: Computer vision and pose estimation. 
• Cao, Z., et al. (2017). OpenPose: Realtime multi-person 2D pose estimation. 
arXiv:1611.08050. - Pose-estimation pipeline for works like Chen et al. (2020). 
• Chen, Y., et al. (2020). Prediction of basketball free throw shooting by OpenPose. - 
Vision-based release parameter estimation; distinct from our ball-physics approach. 
Cluster 3: Kinematics and data sources. 
• Okazaki, V. H. A., et al. (2011). A review on basketball shooting kinematics. Rev. Bras. 
Educ. Fí s. Esporte, 25(4), 665-680. - Empirical release parameter ranges. 
• NBA SportVU / AWS public tracking datasets. - External validation data. 
• Our own filmed dataset (20-30 free throws, mobile camera at 60 fps). 
• Wiley, S., et al. (2014). Release conditions for successful and unsuccessful free throws. J. 
Sports Sci., 32(12), 1148-1154. - Calibrating parameter sweep ranges. 
Research gap: Most existing simulations either (a) ignore backspin and Magnus lift, (b) do 
not separate swish from rim-bounce outcomes, or (c) treat the rim as flexible. The 
OpenPose approach focuses on posture correction rather than ball physics. No recent study 
combines (i) a single fixed restitution constant, (ii) rigid board and rim, (iii) explicit swish 
vs. rim-bounce vs. board-bounce comparison, and (iv) a single error number against 
external data. This benchmark is our contribution. 

5. Feasibility, Limitations, and Ethics 
Feasibility: The equations of motion (drag + Magnus + gravity) are well-established and 
implementable in Python/numpy quickly. RK4 integration and sphere-plane/torus collision 
detection are standard problems with reference implementations. A single smartphone at 
60 fps suffices for data collection. Parameter sweeps over a grid of release conditions 
complete in minutes to hours on a standard laptop. 
Constants and data: All physics constants (g, rho_air, C_d, S, ball mass, ball radius, restitution 
e, board/rim geometry) are hard-coded as Python consts and frozen after initial derivation - 
not tuned to the dataset. Validation uses NBA SportVU open data and 20-30 filmed free 
throws. 
Limitations we will explicitly state: 
• Rigid board and rim - real rims flex and boards vibrate; rim-bounce-in outcomes will be 
less accurate than swish outcomes. 
• Single restitution constant e is a simplification; real board and rim contacts have 
different e values. 
• Spin decay in air beyond Magnus force is not modelled; spin is held constant during 
flight. 
• Small empirical sample - the error number is a sanity check, not a statistically strong 
claim. 
• We will not claim the model predicts real-player performance - only that it is physically 
consistent under stated simplifications. 
Ethics: All filmed participants are group members who give verbal consent. Footage is used 
only to label shot outcomes; no identifying face data is required. Footage is stored locally 
and deleted after the final report. NBA SportVU data is public and anonymised. 
6. Timeline and Team Roles 
Phase 1 (Weeks 1-3): Literature review and physics model design. He Runlong and Li 
Zhenyi derive equations of motion and set up numerical integration. Shao Linjun researches 
collision detection. Liang Xuanshuo sources SportVU data and sets up filming. Chen Yin 
begins introduction and literature review. 
Phase 2 (Weeks 4-6): Core simulation. Li Zhenyi implements RK4 integrator with drag and 
Magnus effects. Shao Linjun implements backboard and rim collision detection. He Runlong 
validates against Brancazio (1981). Liang Xuanshuo begins filming. Chen Yin drafts methods 
section. 
Phase 3 (Weeks 7-9): Extension and validation. Li Zhenyi extends simulation to 3-point 
shots. Liang Xuanshuo processes footage and extracts outcome labels. All members 
contribute to error analysis and validation. 

Phase 4 (Weeks 10-12): Integration, visualisation, and writing. Chen Yin coordinates final 
report and figure consistency. All members review and refine. Final submission and 
presentation. 
Roles may shift as the project progresses, but the named owners are the first point of 
contact for each milestone. 
7. Expected Outcomes 
• Working Python simulation predicting free-throw outcomes from release geometry and 
backspin. 
• Make-probability heatmap showing success variation with release angle, height, and 
backspin. 
• Quantitative validation against real-world dataset, reporting agreement rate. 
• Comparative analysis of free-throw vs. 3-point shot physics. 
• Preliminary feasibility assessment of an AI-based extension for future work.

---

**转换提示**

- PDF 文本由 pypdf 提取；图片、表格结构与扫描件内容未提取。
