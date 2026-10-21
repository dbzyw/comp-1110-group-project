# Basketball Shot Simulation — Project Specification

> Consolidated canonical edition (2026-10-21). This document combines the
> original specification with the expanded model, experiment, validation, and
> implementation details; use it in place of the former separate draft.

## 1. Purpose

This document specifies the scope, model, expected behaviour, and deliverables of the COMP1110 basketball shot simulation. It consolidates the project plans and current implementation and report documentation. Where the early plans differ from the implemented project, this specification describes the current 3D model as the primary research simulation and identifies the 2D simulator as a separate interactive demonstration.

## Table of contents

1. Purpose · 2. Overview · 3. Scope · 4. Primary 3D model · 5. Experiments & analysis · 6. 2D interactive simulator · 7. Quality requirements & limitations · 8. Deliverables & acceptance · 9. Related project documents

## 2. Project overview

The project is a deterministic, pure-physics simulation of basketball shots. Given a ball release position, initial velocity, and backspin rate, it integrates the ball's trajectory and classifies the result. It models gravity, quadratic air drag, Magnus lift, and collisions with a rigid backboard and rim. It does not train a machine-learning model.

The primary research question is:

> Given a release point, initial velocity, and backspin, can a pure-physics model with rigid board and rim geometry and a fixed restitution coefficient reproduce swish, rim-in, board-in, and miss outcomes, and how often does it disagree with labelled real shots?

The free throw is the primary case. A three-point shot comparison examines how launch conditions and aerodynamic effects change with distance. Since the code-merge (`bc7b400` 精简三套.py), the 3D research model and the frozen-constant 2D demo model coexist in the same modules (`physics.py`, `collision.py`, `simulation.py`, `experiment.py`) with clearly separated constant sets (`*_2D` names); they remain two distinct models, not one.

## 3. Scope

### 3.1 In scope

- Release position `(x, y, z)`, initial velocity `(vx, vy, vz)`, and backspin rate.
- Three-dimensional ball flight under gravity, quadratic air drag, and spin-driven Magnus lift.
- Fourth-order Runge–Kutta (RK4) integration and vectorised batch simulation.
- Rigid backboard and rim collision detection, with a normal restitution coefficient; edge/corner geometry, batch detection, position de-penetration, and bounded multi-contact handling (§4.4).
- Four mutually exclusive outcome labels: `swish`, `rim-in`, `board-in`, and `miss`.
- Parameter sweeps over release angle and backspin, with launch-condition jitter, to estimate make probability (free-throw and three-point variants, 17 × 17 grids, 100 jittered shots per cell).
- A second sweep family on the 2D layer: per-cell "scoring speed window" statistics (150 speeds across 5.5–14.5 m/s, widest-window + midpoint re-simulation) written to `data_2d*.csv`.
- Trajectory and probability visualisations, including a free-throw versus three-point comparison, an outcome-subtype breakdown plot, and a Plotly interactive trajectory browser.
- A validation pipeline that compares predicted outcomes to recorded labels without using the data to train or tune the model.
- An interactive 2D simulator for demonstration and exploration. Its constants and collision assumptions are separate from the 3D research model.

### 3.2 Out of scope

- Machine-learning correction or training-based outcome prediction.
- Real-time pose estimation or a production video-analysis pipeline.
- Side-spin, wobble, and spin decay during flight.
- Ball deformation, rim flexibility, backboard vibration, or detailed material modelling.
- Player physiology, fatigue, psychology, or claims about an individual player's ability.
- Tuning the frozen 3D physics constants to make the model fit the validation sample.

## 4. Primary model: 3D research simulation

### 4.1 Coordinate system and units

Use a right-handed coordinate system in SI units:

- `x`: from the shooter towards the basket; the shooter is on the negative-x side.
- `y`: vertical, positive upwards.
- `z`: lateral.
- State vector: `[x, y, z, vx, vy, vz]`.

The backboard lies in the plane `x = 0`. The rim centre is `(−0.375, 3.05, 0)` m.

### 4.2 Frozen physical constants

The following constants define the current 3D research model. They are hard-coded in the physics and collision modules and are not fitted to validation labels.

| Parameter | Value |
|---|---:|
| Gravitational acceleration, `g` | `9.81 m/s²` |
| Air density, `rho` | `1.225 kg/m³` |
| Drag coefficient, `C_d` | `0.50` |
| Magnus coefficient parameter, `C_L0` | `1.00` |
| Ball mass | `0.624 kg` |
| Ball radius | `0.12 m` |
| Rim height | `3.05 m` |
| Rim diameter / radius | `0.45 m` / `0.225 m` |
| Rim-centre distance from backboard | `0.375 m` |
| Backboard width / height | `1.8 m` / `1.05 m` |
| Backboard lower edge | `2.9 m` |
| Normal coefficient of restitution, `e` | `0.7` (configurable per surface: `BACKBOARD_RESTITUTION` / `RIM_RESTITUTION`, both defaulting to 0.7) |
| Tangential velocity retention | `TANGENTIAL_RETENTION = 1.0` (default; frictionless) |

### 4.3 Forces and integration

The model applies the following forces:

- Gravity: `F_g = (0, -m g, 0)`.
- Quadratic drag: `F_d = -0.5 rho C_d A |v| v`, where `A = pi R²`.
- Magnus lift: `F_M = 0.5 rho A C_L0 R (omega x v)`.

Pure backspin is defined as `omega = (0, 0, +rate)`, producing upward lift for a forward-moving shot. Spin remains constant during flight.

Integrate the six-component state with classical RK4 using a nominal step of `1 ms`. The implementation supports single-shot integration and vectorised batch stepping for parameter sweeps.

### 4.4 Collision and scoring rules

- Treat the backboard as a finite rigid rectangle and the rim as a rigid circular ring.
- Detect contact from ball-surface geometry, not only from whether the ball centre crosses the object (closest-point-on-rectangle method, so edge and corner contacts are included).
- On an approaching contact, reflect the velocity's normal component using `e = 0.7`; leave its tangential component unchanged by default (tangential retention 1.0).
- Correct penetrated positions where needed to keep the ball outside the contacted geometry.
- When board and rim contacts occur at the same position, `detect_all()` reports both (stable backboard-then-rim order) and `resolve_contacts()` applies material restitution once, then bounded finite rounds that only remove newly inward velocity, with iterated best-reduction position correction that stops instead of oscillating when the overlap is unsatisfiable.
- A shot is made when the ball centre crosses downward through `y = 3.05 m` and its horizontal distance to the rim centre is no greater than `RIM_RADIUS - BALL_RADIUS = 0.105 m`.
- Assign a made shot according to its contact history: no board or rim contact is `swish`; rim contact without board contact is `rim-in`; any board contact is `board-in`. All other shots are `miss`.

### 4.5 Simulation interface and outputs

The core single-shot simulation accepts release position, release velocity, backspin rate, integration step, maximum flight time, and a bounce limit. It returns the outcome and reason, contact history, time samples, and states along the trajectory. Trajectories can be saved as CSV (3D: `trajectory.csv`; 2D library twin: `trajectory_2d.csv`).

The batch and experiment interfaces accept arrays of release positions and velocities. The parameter sweep writes per-condition results to CSV for plotting; every result row carries its sweep configuration (rim distance, nominal speed, release point, seed and seed strategy, jitter σ, dt, flight time limit, bounce limit, grid counts/bounds) as metadata columns so stochastic findings stay traceable.

## 5. Experiments and analysis

### 5.1 Parameter sweep

The baseline 3D sweeps vary:

- Free throw: release angle 30–70 degrees (17 values) × backspin 0–60 rad/s (17 values), nominal speed `7.5 m/s` from the standard free-throw release point `(-4.57, 2.0, 0)` — 4.57 m from the board plane, hence `rim_distance_m = 4.195` in the per-row metadata (distance from release to rim centre).
- Three point: release angle 36–60 degrees (17 values) × backspin 0–60 rad/s (17 values), nominal speed `9.5 m/s`, release `(-7.125, 2.0, 0)`, rim distance `6.75 m`.
- Jitter per grid cell: 100 shots, with angle standard deviation `1 degree` and speed standard deviation `0.1 m/s`.

Estimate make probability as the fraction of simulated shots classified as made. Run free-throw and three-point conditions separately; record each condition's distance and nominal launch speed alongside its results. Peak values may vary slightly with the random seed. Do not present the two peak probabilities as a controlled, like-for-like comparison when their nominal launch speeds differ.

The 2D sweep family (same modules, `*_2D` constants) reports, per grid cell: fraction of the 150 sampled speeds that score, outcome-subtype shares (`SWISH`/`BANK-IN`/`RATTLE-IN`), and the widest contiguous scoring speed band (`band_lo/hi/width/mid`) with the midpoint's exact outcome re-simulated scalar-identically to the interactive UI. `python experiment.py` with no argument runs all four sweeps; `--selfcheck` reproduces CSVs bit-identically in a temporary directory.

### 5.2 Validation

Validation compares physics predictions with observed outcomes; the measured data is for evaluation only, not training or parameter fitting.

Expected CSV columns (exact header, comma-delimited):

```text
shot_id,release_x,release_y,release_z,v0x,v0y,v0z,backspin,actual_outcome
```

Current loader constraints (`validation.py`): `shot_id` must parse as an integer (duplicate IDs warn but load); all seven physical fields must be finite floats; blank rows are skipped, partially-filled rows fail; `run_validation()` turns per-shot simulation errors into logged per-shot failures counted as binary disagreement and excluded from the multi-class matrix.

Recognised detailed labels are `swish`, `rim-in`, `board-in`, and `miss`. Legacy binary labels such as `made`, `in`, `bounce-in` (or `out`, `no`) may be used for made/miss analysis only; they do not provide a four-class ground truth. Case-insensitive.

Report, where the available labels support them:

- Made/miss agreement and disagreement rates.
- Wilson 95% confidence interval for the agreement rate.
- Precision, recall, specificity, F1, and Matthews correlation coefficient (MCC).
- Cohen's kappa and a no-information baseline.
- Four-class confusion matrix and per-class measures for sufficiently detailed outcome labels.

The intended empirical sources are public, anonymised NBA-style tracking data and approximately 20-30 group-member free throws recorded at 60 fps. The validation inputs are separated: `valid_data_2D.csv` contains 300 straight-on approximation rows with `release_z = v0z = 0`, using source shot speed and release angle for horizontal and vertical components; `valid_data_3D.csv` contains 35 tentative supplied-component rows. In the 3D file, positive source `x_m` was negated and `z_m`/`y_m` were tentatively mapped to release height/lateral position, but its source axes, origin, velocity units, spin, and assumed made labels remain unverified. The 2D result is 153/300 agreement (51.00%; Wilson 95% CI [45.37%, 56.61%]); the 3D result is 0/35 agreement (0.00%; Wilson 95% CI [0.00%, 9.89%]). Neither metric is empirical model validation. Dummy or self-consistency data (including `--correlated`) must not be reported as empirical validation. The final real-data validation remains pending. See `data_validation/DATA_SPECIFICATION.md` for the full contract and readiness assessment.

## 6. 2D interactive simulator

`basketball_shot_2d.py` is a standalone 2D x–y simulator with a Matplotlib interface. It provides controls for release height, angle, backspin, speed, and rim distance, plus trajectory animation, air/ideal-arc toggles, presets, and a speed-window scan. A library twin (`simulation.simulate_2d` plus `*_2D` constants in `physics.py`/`collision.py` and the 2D sweeps in `experiment.py`) implements the same model bit-identically for scripts, CI checks, and CSV data.

This is a teaching and exploration interface, not the numerical implementation of the 3D research model. In particular, it uses different constants (m = 0.60 kg, ρ = 1.204, C_d = 0.47, fixed C_L = 0.20, rim radius 0.2287 m, tangential restitution 0.85, plane-crossing board trigger), 2D motion, two rim endpoints, and different outcome names (`SWISH`, `BANK-IN`, `RATTLE-IN`). 2D made-outcome names map to the 3D four-class labels through `collision.canonical_outcome_2d()` purely to unify the label space for plots/validation; its results must still be identified as 2D results and must not be mixed with the 3D model's constants, sweep results, or validation conclusions.

## 7. Quality requirements and limitations

- Keep model constants explicit and fixed for reproducibility.
- Use consistent SI units and the coordinate convention in this specification.
- Preserve the distinction between simulation, parameter sweep, visualisation, and validation responsibilities.
- Keep validation labels and derived results traceable to their input data.
- Document the random seed and sweep configuration when reporting stochastic results (the sweep CSVs embed this per row).
- Run the self-check entry points after code changes: `python basketball_shot_2d.py --check`, `python experiment.py --selfcheck`, `python plotting.py selfcheck`, `python validation.py selfcheck`, plus `test_core.py` / `test_collision.py` / `test_experiment.py`.
- Treat the small planned empirical sample as a sanity check, not as strong evidence of general predictive performance.
- State that rigid contacts, default-e restitution, constant spin, and simplified rim/board geometry limit physical fidelity; bounce-in predictions are especially sensitive to contact approximations.
- Obtain verbal consent for team-member filming, avoid retaining identifying face data, store footage locally, and delete footage after the final report. Use public anonymised tracking data according to its terms.

## 8. Deliverables and acceptance criteria

The project is complete when it provides:

1. A runnable Python implementation of the 3D RK4 flight model and rigid-contact shot classification.
2. Reproducible free-throw and three-point parameter sweeps and make-probability plots (3D probability maps plus the 2D scoring-window CSV family).
3. Trajectory plots, including a vacuum-versus-aerodynamic comparison, a free-throw-versus-three-point comparison, and an outcome-subtype breakdown figure.
4. A working validation pipeline with documented input format and statistical outputs (Wilson CI, kappa, MCC, confusion matrices), and staged validation data with documented provenance gaps.
5. An interactive 2D simulator (script plus no-install `.exe`), demo GIFs, an interactive HTML trajectory browser, and usage/physics documentation clearly marked as a separate model.
6. Tests covering core flight, collision geometry, simulation outcomes, and sweep-output reproducibility.
7. A report that presents assumptions and limitations and clearly distinguishes computed results from pending real-data validation.

## 9. Related project documents

- [Data specification for the validation pipeline](../data_validation/DATA_SPECIFICATION.md)
- [Project plan](./Basketball-Free-Throw-Project-Plan-v2.md)
- [Original project-plan source PDF](./Basketball-Free-Throw-Project-Plan-v2.pdf)
  — the converted variants disagreed on the outcome labels and references.
  Their differences and the selected interpretation are recorded in Appendix B
  of the consolidated plan; the PDF remains the original source.
- [Progress presentation notes (week 6)](./COMP1110_Basketball_Shot_Simulation_Progress-ea2c2143.md)
- [Project README](../README.md) · [Project context and interfaces](../PROJECT_CONTEXT.md)
- [Final report draft](../Report_Draft.md) · [Presentation outline](../Presentation_Outline.md)
- [2D simulator guide](../SIMULATION_2D_GUIDE.md) · [2D simulator physics](../SIMULATION_2D_PHYSICS.md) · [demo gallery](../SIMULATION_2D_DEMOS.md)
- [Collision model notes](../Collision.md) (a byte-identical rename `碰撞.md` exists on the `LZY` branch)
