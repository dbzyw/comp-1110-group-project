# A Physics-Based Simulation of Basketball Free-Throw Outcomes: Release Geometry, Backspin, and Ball Dynamics under Air Drag and Magnus Effects

*COMP1110 Computing and Data Science in Everyday Life — Final Report (Draft)*

---

## Abstract

We build a pure-physics (no machine-learning) simulation of a basketball free throw. The ball is a rigid sphere whose flight is integrated with a fourth-order Runge–Kutta scheme under gravity, quadratic air drag, and spin-driven Magnus lift. The backboard is a rigid vertical plane and the rim a rigid ring; contacts use a single restitution coefficient e = 0.7. Given a release point, an initial velocity vector, and a backspin rate, the model classifies the shot as a *swish*, a *rim-in*, a *board-in*, or a *miss*. A Monte-Carlo sweep over release angle and backspin rate yields a make-probability surface whose peak is **P ≈ 0.77 near 55° and 45 rad/s** for a free throw, and **P ≈ 0.80 near 48° and 49 rad/s** at three-point range. Comparing a vacuum-aimed trajectory with the real flight shows the ball arrives **≈ 40.2 cm low** at the rim plane for a free throw, and **≈ 117 cm low** for a three-pointer (6.75 m) — air drag and Magnus lift matter more at longer range. Validation reports agreement with a Wilson 95% confidence interval and Cohen's kappa against chance; validation against real tracked shots is in progress.

---

## 1. Introduction

Predicting a basketball shot's outcome has been studied from two directions. Pose-estimation systems such as OpenPose (Cao et al., 2017; Chen et al., 2020) correct the shooter's posture but do not model the ball in flight. Classical ballistics models (Brancazio, 1981; Alaways & Hubbard, 2002) describe the trajectory but often drop backspin or simplify rim/board collisions. Few studies combine all three pieces — release geometry, spin-dependent aerodynamics, and rigid-surface contacts — in one simulation. That gap is our benchmark.

Our research question is: **can a simulation with a rigid backboard, a rigid rim, and a single restitution constant e = 0.7 reproduce swish, rim-and-in, board-and-in, and miss?** The only modelled forces are gravity, quadratic (v²) drag, and spin-driven Magnus lift.

This work contributes a self-contained, reproducible Python simulation (RK4 + collision + sweep + validation) and reports a make-probability surface over release angle and backspin, together with a drag-shortfall estimate for a free throw.

---

## 2. Methods

### 2.1 Coordinate System and Parameters

We use a right-handed frame in SI units: **x** points from the shooter toward the hoop, **y** is vertical (up), and **z** is lateral. The backboard is the plane x = 0 and the shooter is on the negative-x side. The rim centre is at (−0.375, 3.05, 0) m (NBA: rim height 3.05 m, rim diameter 0.45 m, rim centre 0.375 m from the board). The ball has mass m = 0.624 kg and radius R = 0.12 m; air density ρ = 1.225 kg/m³.

### 2.2 Forces

Three forces act on the ball:

- Gravity:  **F_g = (0, −mg, 0)**
- Quadratic air drag:  **F_d = − ½ ρ C_d A |v| v**   (C_d = 0.50, A = πR²)
- Magnus lift:  **F_M = ½ ρ A C_L0 R (ω × v)**   (C_L0 = 1.00)

For pure backspin the spin vector is **ω = (0, 0, +ω)**, so ω × v has a positive y-component and lifts the ball. The Magnus term is equivalent to a lift-coefficient form C_L = C_L0 · R|ω|/|v|, i.e. linear in the spin parameter.

### 2.3 Numerical Integration

The state vector is **s = [x, y, z, vx, vy, vz]**. We integrate ds/dt = [vx, vy, vz, ax, ay, az] with a classical fourth-order Runge–Kutta step (dt = 1 ms) in NumPy. A vectorised batch version integrates many shots simultaneously for the parameter sweep. The spin is held constant during flight (no decay).

### 2.4 Collision Model

- **Backboard (plane–sphere):** the ball touches the vertical plane x = 0 when its surface reaches it, provided the contact point lies within the board rectangle (1.8 m wide, 1.05 m tall, bottom edge 2.9 m).
- **Rim (sphere–ring):** the rim is a circle of radius 0.225 m in the plane y = 3.05 m. The ball collides when the distance from its centre to the closest point on the ring is ≤ R.

On contact, only the velocity component along the contact normal is reflected with restitution e = 0.7: **v' = v − (1+e)(v·n)n**. The tangential component is unchanged (no friction, no side-spin).

### 2.5 Scoring Criterion

A shot is *made* when the ball centre crosses the plane y = 3.05 m downward while its horizontal distance to the rim centre is ≤ R_rim − R_ball = 0.105 m. The outcome is then subdivided by contact history: no contact → **swish**; contact with the rim only → **rim-in**; any contact with the backboard → **board-in**; otherwise **miss**. This matches the plan's four-way labelling (swish, rim-and-in, board-and-in, miss).

### 2.6 Parameter Sweep and Validation Design

The sweep varies release angle (30–70°, 17 values) and backspin rate (0–60 rad/s, 17 values); each cell uses 100 Monte-Carlo shots with Gaussian jitter (σ = 1° in angle, σ = 0.1 m/s in speed). Validation compares model outcomes against tracked shots and reports a single disagreement rate (a sanity check, not a statistical claim).

---

## 3. Results

### 3.1 Make-Probability Surface

The angle-vs-backspin sweep produces a make-probability surface (Figure: `make_probability.png`) with a clear interior peak:

- **Peak P(make) ≈ 0.77 at ≈ 55° and ≈ 45 rad/s.**
- The backspin dimension shows a broad plateau (~15–45 rad/s): more backspin adds lift and raises the shot, but too much overshoots.
- Without spin the mean probability is lower, and it rises toward the plateau.

Repeating the sweep at three-point range (6.75 m, release speed 9.5 m/s; Figures: `make_probability_three.png`, `make_probability_comparison.png`) shifts the optimum and re-shapes the surface:

- **Three-point peak P(make) ≈ 0.80 at ≈ 48° and ≈ 49 rad/s**, versus ≈ 0.77 at ≈ 55° and ≈ 45 rad/s for the free throw.
- The optimal release angle is ≈ 7° lower (48° vs 55°): the higher launch speed required to cover 6.75 m favours a flatter arc.
- The optimal backspin is similar (≈ 45–49 rad/s), so strong backspin remains beneficial at range.
- Note the two sweeps use different nominal speeds (7.5 m/s free throw, 9.5 m/s three-point), so the peak *level* is not a like-for-like difficulty comparison; the robust findings are the angle shift and the drag-shortfall growth reported in §3.2.

### 3.2 Vacuum Aim vs. Real Flight

A second experiment aims the ball "as if in a vacuum" (only gravity) at the rim centre, then re-runs the same release with drag and backspin (Figure: `trajectory_comparison.png`):

- With air resistance the ball reaches the rim plane **≈ 40.2 cm low**.
- This quantifies how much the drag-and-Magnus model matters relative to the vacuum idealisation.

A nominal free throw (7.5 m/s, 51°, 23 rad/s) is classified as a **swish** with a horizontal offset of ≈ 5.5 cm from the rim centre.

Extending the same vacuum-aim vs. real-flight experiment to three-point range (6.75 m from the hoop; Figure: `trajectory_comparison_three.png` and `free_vs_three_drag.png`) shows the drag-and-Magnus shortfall grows sharply with distance:

- Free throw: **≈ 40.2 cm low** at the rim plane.
- Three-pointer: **≈ 117 cm low** — more than a full metre, and **≈ 77 cm more** than the free throw.

This is the key comparative result: longer release distance increases flight time and speed, so both quadratic drag and the spin-dependent Magnus lift accumulate more deviation, making them materially more important for three-point shots.

### 3.3 Validation (Preliminary — not yet complete)

The validation pipeline (`validation.py`, read → predict → compare) is implemented and reports, in addition to the raw agreement/disagreement rate:

- **Wilson 95% confidence interval** on the agreement rate — essential for the small (20–30 shot) sample, where a bare proportion is statistically weak.
- **Cohen's kappa** and the no-information (majority-class) baseline, so the number is interpretable relative to chance.
- **Per-class metrics** (precision / recall / F1) and a 4 × 4 confusion matrix over swish / rim-in / board-in / miss.

The pipeline passes a self-consistency check: when the "ground truth" is the model's own prediction, agreement ≈ 100% and kappa ≈ 1.0. On random placeholder labels, agreement is ≈ 35% with kappa ≈ −0.18 (no better than chance, as expected), and a 20-shot agreement of 35% carries a Wilson 95% CI of ≈ [18%, 57%] — a concrete illustration of why a single number alone is not enough. **Validation against real SportVU / self-filmed data is still pending**; the final numbers will be reported here once the data are imported.

---

## 4. Limitations

- **Rigid surfaces:** real rims flex and real backboards vibrate; our contacts are perfectly rigid.
- **One restitution constant** for two different contacts (rim and board).
- **Constant spin:** backspin does not decay in flight, and side-spin/wobble are ignored.
- **Bounce-in accuracy:** board/rim bounces are expected to be less accurate than clean swishes.
- **Small empirical sample:** validation is not yet complete, so the reported disagreement rate will be a sanity check only.

---

## 5. Future Work

- Import real SportVU and self-filmed (60 fps) data to complete the validation and report the disagreement rate.
- Calibrate the three-point launch speed against published release kinematics (Wiley et al., 2014) and re-run the sweep at a matched speed, so free-throw and three-point peak levels become a like-for-like difficulty comparison.
- Add spin decay, rim flex, and a rim-vs-board-specific restitution.
- A written note on a possible AI-based extension (pose estimation), kept out of scope for the physics model.

---

## References

1. Cao, Z., Simon, T., Wei, S.-E., & Sheikh, Y. (2017). Realtime multi-person 2D pose estimation using Part Affinity Fields. *CVPR*.
2. Chen, Y. et al. (2020). Pose-based feedback for shooting kinematics.
3. Brancazio, P. J. (1981). Physics of basketball. *American Journal of Physics*, 49(4).
4. Alaways, L. W., & Hubbard, M. (2002). Experimental determination of baseball spin and lift. *Journal of Sports Sciences*.

*(Reference list to be completed and formatted to the required citation style.)*
