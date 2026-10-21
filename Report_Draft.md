# A Physics-Based Simulation of Basketball Shot Outcomes: Release Geometry, Backspin, and Ball Dynamics under Air Drag and Magnus Effects

*COMP1110 Computing and Data Science in Everyday Life — Final Report (Draft)*

**Keywords:** basketball, projectile motion, RK4, air drag, Magnus lift, coefficient of restitution, Monte-Carlo sweep, validation metrics

## Table of contents

- Abstract
- 1. Introduction
- 2. Methods — 2.1 Coordinates / 2.2 Forces / 2.3 RK4 / 2.4 Collisions / 2.5 Scoring / 2.6 Sweep & validation design
- 3. Results — 3.1 Make-probability surface / 3.2 Vacuum vs real flight / 3.3 Validation (preliminary)
- 4. Discussion · 5. Ethics · 6. Conclusion · 7. Future Work · References

---

## Abstract

We build a pure-physics (no machine-learning) simulation of basketball shot outcomes. The ball is treated as a rigid sphere whose flight is integrated with a fourth-order Runge–Kutta scheme under gravity, quadratic air drag, and spin-driven Magnus lift. The backboard is a rigid vertical plane and the rim a rigid ring; contacts use a single restitution coefficient e = 0.7. Given a release point, an initial velocity vector, and a backspin rate, the model classifies the shot as a *swish*, a *rim-in*, a *board-in*, or a *miss*. The executed Monte-Carlo sweeps (17 × 17 parameter cells, 100 jittered shots per cell) yield a free-throw peak of **P ≈ 0.77 near 55° and 45 rad/s** and a three-point peak of **P ≈ 0.79 near 45° and 37.5 rad/s**; the latter peak consists entirely of board-in outcomes in this model. Comparing a vacuum-aimed trajectory with the real flight shows the ball arrives **≈ 40.2 cm low** at the rim plane for a free throw and **≈ 117.4 cm low** for a three-pointer (6.75 m). The validation pipeline reports agreement with a Wilson 95% confidence interval and Cohen's kappa, but its current 305-row dataset uses assumed release inputs and binary labels, so these metrics are not empirical validation results.

---

## 1. Introduction

Predicting a basketball shot's outcome has been studied from two directions. Pose-estimation systems such as OpenPose (Cao et al., 2017; Nakai et al., 2018) correct the shooter's posture but do not model the ball in flight. Classical ballistics models (Brancazio, 1981; Okubo & Hubbard, 2006) describe the trajectory but often drop backspin or simplify rim/board collisions. Few studies combine all three pieces — release geometry, spin-dependent aerodynamics, and rigid-surface contacts — in one simulation. That gap is our benchmark.

Our research question is: **can a simulation with a rigid backboard, a rigid rim, and a single restitution constant e = 0.7 reproduce swish, rim-in, board-in, and miss?** The only modelled forces are gravity, quadratic (v²) drag, and spin-driven Magnus lift.

This work contributes a self-contained, reproducible Python simulation (RK4 + collision + sweep + validation) and reports a make-probability surface over release angle and backspin, together with a drag-shortfall estimate for both free throws and a three-point shot.

---

## 2. Methods

### 2.1 Coordinate System and Parameters

We use a right-handed frame in SI units: **x** points from the shooter toward the hoop, **y** is vertical (up), and **z** is lateral. The backboard is the plane x = 0 and the shooter is on the negative-x side. The rim centre is at (−0.375, 3.05, 0) m (NBA: rim height 3.05 m, rim diameter 0.45 m, rim centre 0.375 m from the board). The ball has mass m = 0.624 kg and radius R = 0.12 m; air density ρ = 1.225 kg/m³.

### 2.2 Forces

Three forces act on the ball:

- Gravity: **F_g = (0, −mg, 0)**
- Quadratic air drag: **F_d = − ½ ρ C_d A |v| v** (C_d = 0.50, A = πR²)
- Magnus lift: **F_M = ½ ρ A C_L0 R (ω × v)** (C_L0 = 1.00)

For pure backspin the spin vector is **ω = (0, 0, +ω)**, so ω × v has a positive y-component and lifts the ball. The Magnus term is equivalent to a lift-coefficient form C_L = C_L0 · R|ω|/|v|, i.e. linear in the spin parameter.

### 2.3 Numerical Integration

The state vector is **s = [x, y, z, vx, vy, vz]**. We integrate ds/dt = [vx, vy, vz, ax, ay, az] with a classical fourth-order Runge–Kutta step (dt = 1 ms) in NumPy. A vectorised batch version integrates many shots simultaneously for the parameter sweep. The spin is held constant during flight (no decay).

### 2.4 Collision Model

- **Backboard (plane–sphere):** the ball touches the vertical plane x = 0 when its surface reaches it, provided the contact point lies within the board rectangle (1.8 m wide, 1.05 m tall, bottom edge 2.9 m). Contact is detected from the closest point on the rectangle, so edge and corner hits are included.
- **Rim (sphere–ring):** the rim is a circle of radius 0.225 m in the plane y = 3.05 m. The ball collides when the distance from its centre to the closest point on the ring is ≤ R.

On contact, only the velocity component along the contact normal is reflected with restitution e = 0.7: **v' = v − (1 + e)(v · n)n**. The tangential component is unchanged (the model's default tangential-retention parameter is 1.0, i.e. no friction, no side-spin); a bounded finite-round correction handles simultaneous board-and-rim contacts.

### 2.5 Scoring Criterion

A shot is *made* when the ball centre crosses the plane y = 3.05 m downward while its horizontal distance to the rim centre is ≤ R_rim − R_ball = 0.105 m. The outcome is then subdivided by contact history: no contact → **swish**; contact with the rim only → **rim-in**; any contact with the backboard → **board-in**; otherwise **miss**. This matches the four-way labelling set out in the project specification.

### 2.6 Parameter Sweep and Validation Design

The sweep varies release angle (30–70°, 17 values) and backspin rate (0–60 rad/s, 17 values); each cell uses 100 Monte-Carlo shots with Gaussian jitter (σ = 1° in angle, σ = 0.1 m/s in speed). Validation compares model outcomes against tracked shots and reports disagreement rate, Wilson 95% confidence intervals, and Cohen's kappa as a simple but principled summary of performance. Every result row carries its sweep configuration (distance, nominal speed, seed, jitter σ, grid bounds) as metadata columns, so stochastic findings remain traceable and reproducible.

---

## 3. Results

### 3.1 Make-Probability Surface

The angle-vs-backspin sweep produces a make-probability surface with a clear interior peak (figures: `make_probability.png`, `make_probability_three.png`, `make_probability_comparison.png`; subtype split: `outcome_breakdown.png`):

- **Peak P(make) ≈ 0.77 at ≈ 55° and ≈ 45 rad/s.**
- The backspin dimension shows a broad plateau (~15–45 rad/s): more backspin adds lift and raises the shot, but too much overshoots.
- Without spin the mean probability is lower, and it rises toward the plateau.

Repeating the sweep at three-point range (6.75 m, release speed 9.5 m/s, angle grid 36–60°) shifts the optimum and re-shapes the surface:

- **Three-point peak P(make) = 0.79 at 45° and 37.5 rad/s**, versus **0.77 at 55° and 45 rad/s** for the free throw.
- The peak angle is 10° lower (45° vs 55°) and the peak backspin is 7.5 rad/s lower in this run.
- The three-point peak cell is entirely **board-in** (P(board-in) = 0.79); the free-throw peak is P(swish) = 0.52, P(rim-in) = 0.15, and P(board-in) = 0.10. This dependence on contact history should be interpreted alongside the model's rigid-contact assumptions.
- Note the two sweeps use different nominal speeds (7.5 m/s free throw, 9.5 m/s three-point), so the peak level is not a like-for-like difficulty comparison; the robust findings are the angle shift and the drag-shortfall growth reported below.

### 3.2 Vacuum Aim vs. Real Flight

A second experiment aims the ball “as if in a vacuum” (only gravity) at the rim centre, then re-runs the same release with drag and backspin (figures: `trajectory_comparison.png`, `trajectory_comparison_three.png`, `free_vs_three_drag.png`). The result is a systematic shortfall relative to the ideal trajectory:

- With air resistance the ball reaches the rim plane **≈ 40.2 cm low** for a free throw.
- The same comparison at three-point range shows a shortfall of **≈ 117.4 cm low**.

A nominal free throw (7.5 m/s, 51°, 23 rad/s) is classified as a **swish** with a horizontal offset of ≈ 5.5 cm from the rim centre.

This is the key comparative result: longer release distance increases flight time and speed, so both quadratic drag and the spin-dependent Magnus lift accumulate more deviation, making them materially more important for three-point shots.

### 3.3 Validation (Preliminary — not yet complete)

The validation pipeline (`validation.py`, read → predict → compare) is implemented and reports, in addition to the raw agreement/disagreement rate:

- **Wilson 95% confidence interval** on the agreement rate — essential for the small (20–30 shot) sample, where a bare proportion is statistically weak.
- **Cohen's kappa** and the no-information baseline, plus precision/recall/specificity/F1/MCC for the binary made-vs-miss split.
- **Four-class confusion matrix** with per-class precision/recall/F1.

The validation design is 20–30 group-member free throws recorded at 60 fps plus public NBA SportVU tracking. The inputs are separated to prevent a straight-on approximation being presented as 3D data. `valid_data_2D.csv` contains 300 rows with `release_z = v0z = 0` and uses the source `Shot_Speed_m_s` and `Release_Angle_deg` to resolve its horizontal and vertical velocity components; its result is **153/300 agreement (51.00%; Wilson 95% CI [45.37%, 56.61%])**. `valid_data_3D.csv` contains 35 tentative supplied-component rows; positive source `x_m` was negated and `z_m`/`y_m` were tentatively mapped to height/lateral position. Its result is **0/35 agreement (0.00%; Wilson 95% CI [0.00%, 9.89%])**. The 3D source axes, origin, velocity units, spin, and labels remain unverified; the 2D input's lateral motion and source-angle semantics are also assumptions. Neither result is evidence of model performance; they measure the respective assumptions and labels, not observed shot kinematics.

The random 20-row placeholder run gave 7/20 agreement (35.0%; Wilson 95% CI [18.1%, 56.7%], κ = −0.182), while the self-consistent dummy self-check gave 20/20 (100%; Wilson 95% CI [83.9%, 100%], κ = 1.000). These are pipeline checks, not validation evidence. Automated checks run for this revision passed: core tests (13/13), collision tests (24/24), experiment tests (2/2), the 2D demo check (6/6), experiment reproducibility self-check (3/3), plot self-check (7/7), and validation self-check. Empirical validation remains incomplete until measured release inputs, backspin, outcome labels, units, and coordinate conventions are documented.

---

## 4. Discussion

The central conclusion is that a small physics model can generate varied basketball shot outcomes without learning from data. In the executed sweeps, the free-throw peak is near 55° and 45 rad/s, while the three-point peak is near 45° and 37.5 rad/s; the latter is dominated by board-in outcomes. The vacuum-aim comparison also shows a larger shortfall at three-point range. These are simulation results, not claims about empirical accuracy; the chosen nominal speeds differ and the current validation dataset does not contain measured shot kinematics.

The limitations are also explicit. The model assumes rigid board and rim surfaces, fixed restitution e = 0.7, and constant spin during flight; it does not model ball deformation, rim flexing, or board vibration. Real-world shot trajectories are noisier than the deterministic model, and the validation sample is still small. These are not weaknesses in the code alone but deliberate boundaries of the project scope. A separate interactive 2D demonstration (`basketball_shot_2d.py`) deliberately uses a different frozen constant set (m = 0.60 kg, ρ = 1.204, C_d = 0.47, C_L = 0.20, plus tangential restitution 0.85); its results are reported only as a teaching aid and must not be merged numerically with the 3D findings above.

---

## 5. Ethics and Data Handling

The project uses only group-member footage and public anonymised tracking data. Filming is done with verbal consent; only outcome labels and release parameters are kept, not identifying face data. The project does not make claims about athlete performance beyond the physics of the shot itself, and all footage is kept local unless explicitly required for reporting.

---

## 6. Conclusion

This project demonstrates that a pure-physics simulation can generate distinct shot outcomes, estimate the effects of backspin and air drag, and show how the vacuum-aim shortfall changes with distance. The implementation and its scan/plot/validation checks are executable and reproducible. Its empirical accuracy has not yet been established; the next step is to import a properly labelled dataset with measured release position, velocity, backspin, and outcome, then report the disagreement rate with Wilson intervals and kappa.

---

## 7. Future Work

- Import real SportVU and self-filmed (60 fps) data to complete the validation and report the disagreement rate.
- Calibrate the three-point launch speed against published release kinematics and re-run the sweep at a matched speed, so free-throw and three-point peak levels become a like-for-like difficulty comparison.
- Add spin decay, rim flex, and a rim-vs-board-specific restitution.
- Recover original-precision tracking timestamps and confirm the source coordinate convention before deriving release velocities from tracks (see `data_validation/DATA_SPECIFICATION.md`).
- Keep a written note on a possible AI-based extension (pose estimation) out of scope for the main physics model.

---

## References

1. Cao, Z., Simon, T., Wei, S.-E., & Sheikh, Y. (2017). Realtime multi-person 2D pose estimation using Part Affinity Fields. *CVPR*.
2. Nakai, M., Tsunoda, Y., Hayashi, H., & Murakoshi, H. (2018). Prediction of basketball free throw shooting by OpenPose. In *New Frontiers in Artificial Intelligence* (JSAI-isAI 2018). Springer.
3. Brancazio, P. J. (1981). Physics of basketball. *American Journal of Physics*, 49(4), 356–365.
4. Okubo, H., & Hubbard, M. (2006). Dynamics of the basketball shot with application to the free throw. *Journal of Sports Sciences*, 24(12), 1303–1314.
5. Hamilton, G. R., & Reinschmidt, C. (1997). Optimal trajectory for the basketball free throw. *Journal of Sports Sciences*, 15(5), 491–504.
6. Tran, C. M., & Silverberg, L. M. (2008). Optimal release conditions for the free throw in men's basketball. *Journal of Sports Sciences*, 26(11), 1147–1155.
7. White, C. (2011). *Projectile Dynamics in Sport: Principles and Applications*. Routledge.
8. Okazaki, V. H. A., Rodacki, A. L. F., & Satern, M. N. (2015). A review on the basketball jump shot. *Sports Biomechanics*, 14(2), 190–205.
