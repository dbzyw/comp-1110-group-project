# A Physics-Based Simulation of Basketball Shot Outcomes: Release Geometry, Backspin, and Ball Dynamics under Air Drag and Magnus Effects

*COMP1110 Computing and Data Science in Everyday Life — Final Report (Draft)*

> This is an improved draft of `Report_Draft.md` (2026-10-21); the original file is kept
> unchanged in the same folder. Changes: added a table of contents and keywords, pinned
> figure files to the plotting outputs, updated §3.3 with the current `data_validation/`
> status, cited Tran & Silverberg (2008), and disambiguated the no-friction wording.

**Keywords:** basketball, projectile motion, RK4, air drag, Magnus lift, coefficient of restitution, Monte-Carlo sweep, validation metrics

## Table of contents

- Abstract
- 1. Introduction
- 2. Methods — 2.1 Coordinates / 2.2 Forces / 2.3 RK4 / 2.4 Collisions / 2.5 Scoring / 2.6 Sweep & validation design
- 3. Results — 3.1 Make-probability surface / 3.2 Vacuum vs real flight / 3.3 Validation (preliminary)
- 4. Discussion · 5. Ethics · 6. Conclusion · 7. Future Work · References

---

## Abstract

We build a pure-physics (no machine-learning) simulation of basketball shot outcomes. The ball is treated as a rigid sphere whose flight is integrated with a fourth-order Runge–Kutta scheme under gravity, quadratic air drag, and spin-driven Magnus lift. The backboard is a rigid vertical plane and the rim a rigid ring; contacts use a single restitution coefficient e = 0.7. Given a release point, an initial velocity vector, and a backspin rate, the model classifies the shot as a *swish*, a *rim-in*, a *board-in*, or a *miss*. A Monte-Carlo sweep over release angle and backspin rate yields a make-probability surface whose peak is **P ≈ 0.77 near 55° and 45 rad/s** for a free throw, and **P ≈ 0.80 near 48° and 49 rad/s** at three-point range. Comparing a vacuum-aimed trajectory with the real flight shows the ball arrives **≈ 40.2 cm low** at the rim plane for a free throw, and **≈ 117 cm low** for a three-pointer (6.75 m) — air drag and Magnus lift matter more at longer range. Validation reports agreement with a Wilson 95% confidence interval and Cohen's kappa against chance; final validation against real tracked shots is still in progress.

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

- **Three-point peak P(make) ≈ 0.80 at ≈ 48° and ≈ 49 rad/s**, versus ≈ 0.77 at ≈ 55° and ≈ 45 rad/s for the free throw.
- The optimal release angle is ≈ 7° lower (48° vs 55°): the higher launch speed required to cover 6.75 m favours a flatter arc.
- The optimal backspin is similar (≈ 45–49 rad/s), so strong backspin remains beneficial at range.
- Note the two sweeps use different nominal speeds (7.5 m/s free throw, 9.5 m/s three-point), so the peak level is not a like-for-like difficulty comparison; the robust findings are the angle shift and the drag-shortfall growth reported below.

### 3.2 Vacuum Aim vs. Real Flight

A second experiment aims the ball “as if in a vacuum” (only gravity) at the rim centre, then re-runs the same release with drag and backspin (figures: `trajectory_comparison.png`, `trajectory_comparison_three.png`, `free_vs_three_drag.png`). The result is a systematic shortfall relative to the ideal trajectory:

- With air resistance the ball reaches the rim plane **≈ 40.2 cm low** for a free throw.
- The same comparison at three-point range shows a shortfall of **≈ 117 cm low**.

A nominal free throw (7.5 m/s, 51°, 23 rad/s) is classified as a **swish** with a horizontal offset of ≈ 5.5 cm from the rim centre.

This is the key comparative result: longer release distance increases flight time and speed, so both quadratic drag and the spin-dependent Magnus lift accumulate more deviation, making them materially more important for three-point shots.

### 3.3 Validation (Preliminary — not yet complete)

The validation pipeline (`validation.py`, read → predict → compare) is implemented and reports, in addition to the raw agreement/disagreement rate:

- **Wilson 95% confidence interval** on the agreement rate — essential for the small (20–30 shot) sample, where a bare proportion is statistically weak.
- **Cohen's kappa** and the no-information baseline, plus precision/recall/specificity/F1/MCC for the binary made-vs-miss split.
- **Four-class confusion matrix** with per-class precision/recall/F1.

The validation design uses 20–30 group-member free throws recorded at 60 fps plus public NBA SportVU tracking. Status as of this revision (2026-10-21): `data_validation/` holds a SportVU-style ball-track extraction (24,073 frame records over 49 events; the export flattened timestamps to one rounded scientific-notation value, so millisecond ordering is lost; source axes/origin are still unconfirmed) and five selected release position/velocity records whose units and shot linkage are not yet documented. The earlier 300-row placeholder template (binary `made`/`miss` only, all seven physical inputs blank) has been removed from the branch while its source dataset is re-verified. Dummy runs confirm the metric chain end-to-end (`python validation.py selfcheck`: agreement = 100%, κ > 0.99 on self-consistent data; uncorrelated labels give ≈ 35% with κ ≈ −0.18, the random baseline). The final empirical agreement numbers against real tracked shots remain to be filled in once release parameters, spin and outcome labels are derived with documented conventions.

---

## 4. Discussion

The central conclusion is that a small physics model can reproduce the qualitative behaviour of a basketball shot without learning from data. The free throw and three-point sweep both show a reasonably well-defined optimum in release angle and backspin, and the drag-and-Magnus effect grows with distance. This is consistent with the problem specification, with the literature on ball flight, and with published optimal free-throw release conditions (Tran & Silverberg, 2008, who locate the optimum band near 50–55°), while remaining deliberately simple enough to run fast and transparently.

The limitations are also explicit. The model assumes rigid board and rim surfaces, fixed restitution e = 0.7, and constant spin during flight; it does not model ball deformation, rim flexing, or board vibration. Real-world shot trajectories are noisier than the deterministic model, and the validation sample is still small. These are not weaknesses in the code alone but deliberate boundaries of the project scope. A separate interactive 2D demonstration (`basketball_shot_2d.py`) deliberately uses a different frozen constant set (m = 0.60 kg, ρ = 1.204, C_d = 0.47, C_L = 0.20, plus tangential restitution 0.85); its results are reported only as a teaching aid and must not be merged numerically with the 3D findings above.

---

## 5. Ethics and Data Handling

The project uses only group-member footage and public anonymised tracking data. Filming is done with verbal consent; only outcome labels and release parameters are kept, not identifying face data. The project does not make claims about athlete performance beyond the physics of the shot itself, and all footage is kept local unless explicitly required for reporting.

---

## 6. Conclusion

This project demonstrates that a pure-physics simulation can generate realistic shot outcomes, estimate the effect of backspin and air drag, and explain why longer shots are more sensitive to aerodynamic losses. The current implementation is executable, reproducible, and ready for further validation against real tracked shots. The next step is to import a properly labelled dataset, run the full validation pipeline, and quantify the disagreement rate with Wilson intervals and kappa.

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
