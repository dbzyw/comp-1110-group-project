# Audit Plan — logic audit & surgical repair of all `.py` files (COMP1110 basketball shot simulator)

Scope: 14 files. Ground-truth `.md` docs are the authority over code; where a doc is
self-contradictory, report the ambiguity — do not guess. Builders: surgical repair only,
no refactor/rename/reformat, capture before/after numeric probes, never touch `test_*.py`.

## 1. Module dependency seams & cross-file invariants

Import graph (arrows = "imports from"):
```
physics.py ──► collision.py ──► simulation.py ──► experiment.py
                │                    │
                │                    └──► validation.py   (uses simulate_shot only)
                └──► plotting.py      (uses physics.integrate + collision geom; NOT simulation)
                     make_interactive.py (uses simulation.simulate_shot + physics + collision)
basketball_shot_2d.py  = standalone duplicate of the 2D layer (must stay behaviour-equal)
data_validation/data_prep.py, data_validation/extract.py = standalone (no project imports)
```
Two models coexist in the same files (physics/collision/simulation/experiment):
3D main flow (no suffix) and 2D demo layer (`*_2D`/`*_2d`). Constants are **NOT
interchangeable** (README §4). Every report must state which layer it touched.

Cross-file invariants a repair must preserve (change only if a ground-truth doc proves the current behaviour wrong):
- **State layout**: 3D `[x,y,z,vx,vy,vz]` (pos 0:3, vel 3:6); 2D `[x,y,vx,vy]`. float64, finite.
- **Units**: SI (m, s, kg, rad/s).
- **Axes**: +x shooter→hoop (backboard plane x=0), +y up, +z lateral (right-handed); shooter at −x; `RIM_CENTER=(-0.375, 3.05, 0)`.
- **Backspin sign (3D)**: ω=(0,0,+rate) ⇒ upward Magnus lift (physics.md §3.2/§4.3; `test_core.test_magnus_backspin_gives_upward_lift`). 2D: ωz = spin·sinθ (`physics.spin_in_plane_2d`).
- ⚠️ **2D Magnus sign ambiguity (highest-value look-here)**: 3D `magnus_force = ½ρAC_L0R·(ω×v)` (physics.py:100). 2D `acceleration_2d` Magnus = `(+BM·ωz·vy, −BM·ωz·vx)` (physics.py:342-343) = **−(ω×v)**. SIMULATION_2D_PHYSICS.md §3 writes this exact formula but claims "ω×v 展开后 … 后旋→升力向上", and §7 claims "力 ∝ ω×v" — both contradicted by the code sign (for a rising forward shot with ωz>0 the code gives **downward** ay). This is either a genuine sign error, a frozen-deck convention, or a self-contradictory doc. **Do NOT silently flip it**; report the doc-vs-code-vs-3D cross-reference. Same formula is duplicated in `basketball_shot_2d.py` `dv()` and `experiment._dv2` — all three must be decided together.
- **Outcome vocab**: 3D `swish`/`rim-in`/`board-in`/`miss`. 2D `SWISH`/`BANK-IN`/`RATTLE-IN` + miss strings ("off the board, out", "off the rim, out", "past the board, lands behind", "long miss, past the hoop", "short, low at the rim plane", "well short"). `canonical_outcome_2d`: SWISH→swish, BANK-IN→board-in, RATTLE-IN→rim-in, else miss (collision.py:660-670).
- **Scoring**: 3D `SCORE_RADIUS = RIM_RADIUS − BALL_RADIUS = 0.105` (simulation.py:35 AND experiment.py:87 — keep equal). 2D: downward crossing of y=3.05 with x∈(xF+0.012, xB−0.012) (`detect_scoring_cross_2d`; same in `simulate_2d` and `batch_simulate_2d`).
- **Restitution**: 3D `BACKBOARD_RESTITUTION = RIM_RESTITUTION = 0.7`, `TANGENTIAL_RETENTION = 1.0` (collision.py:76-82). 2D `RESTITUTION_NORMAL_2D = 0.70`, `RESTITUTION_TANGENTIAL_2D = 0.85` (physics.py:316-317).
- **Geometry**: `RIM_HEIGHT=3.05`; `RIM_RADIUS` 0.225 (3D) vs 0.2287 (2D); `BOARD_OFFSET_2D=0.15`; `xbc = xB + 0.15 − 0.12` (`hoop_geometry_2d`).
- **CSV contracts**: `trajectory.csv` = `time,x,y,z,vx,vy,vz`; `trajectory_2d.csv` = `time,x,y,vx,vy`; `data.csv`/`data_three.csv` = `angle,backspin,p_make,p_swish,p_rim_in,p_board_in`+metadata cols; `data_2d*.csv` = `angle,backspin,p_speed_made,p_swish,p_bank_in,p_rattle_in,n_scored,band_lo,band_hi,band_width,band_mid,outcome_at_mid,...`; validation CSV = 9 cols `shot_id,release_x,release_y,release_z,v0x,v0y,v0z,backspin,actual_outcome`.

## 2. Defect taxonomy — evidence required before calling something a defect

"no defect found" is a valid outcome. A fix is justified only with the listed evidence:
1. **Formula/constant mismatch vs docs** — cite doc line + code line + numeric divergence (e.g. wrong γ/β/BM/BD, wrong cross term, wrong landing plane).
2. **Sign / axis error** — a sign or index contradicting the documented convention (physics.md §1/§4.3, Collision.md §1). Prime target = the 2D Magnus item in §1; resolve doc-vs-code first.
3. **Off-by-one / index** — state slice, frame loop `range(int(max_t/dt))` boundary, `mid_i=(lo+hi)//2` vs documented SCAN-WINDOW midpoint rule (experiment.band_from_flags).
4. **Degenerate-input crash** — ZeroDivisionError, sqrt/log of non-positive, tan(±90°), NaN for v=0 / θ=90° / margin closing hoop window / h0 below landing plane; evidence = a concrete input that tracebacks or yields NaN instead of a documented clean error/None.
5. **Silent NaN/inf** — a path that writes NaN/inf into a result/CSV with no guard.
6. **Shared-state mutation / alias return** — module mutable mutated in place, or a function returning an input alias (collision.reflect formerly aliased; confirm the copy fix held and no other alias returns exist).
7. **Drifted duplicate logic** — same concept implemented twice with divergence. Two hotspots: (a) standalone `basketball_shot_2d.py` vs the library 2D layer (must stay behaviour-equal; cross-check = 6 DEMO scenes + `test_core`); (b) `experiment.batch_simulate` inline collision vs `simulation.simulate_shot`/`collision.resolve_contacts` (see §3). Evidence = same inputs, divergent outputs.
8. **Docstring/code contradiction** — `.py` docstring contradicts code. Ground-truth `.md` wins over a `.py` docstring; align code to the `.md`, or report.
9. **Resource leak** — unclosed `open()` / `os.fdopen` without `with`, leaked fd in `_write_*_atomic`.
10. **Wrong boundary/branch condition** — `<` vs `<=`, `>` vs `>=`, `and` vs `or` in contact/scoring/landing. NOTE: the counter-intuitive 2D miss branch order ("long" vs "short") is **documented** (SIMULATION_2D_PHYSICS.md §4) — do NOT "fix" it.

## 3. Cross-file risk list (what each builder must NOT change)

- **physics.py**: public constants + signatures (everything else imports them). Do NOT change the 2D Magnus sign unilaterally — it ripples to collision/simulation/experiment/basketball_shot_2d and the 6 doc scenes.
- **collision.py**: `Collision` field order `(kind, normal, penetration, contact)`; module constant names (test_collision `patch.object`s them); `detect_all` backboard-then-rim order; normal direction ("from surface toward ball"); `reflect` copy semantics.
- **simulation.py**: `simulate_shot` dict keys (`outcome/reason/contacted/has_hit_rim/has_hit_board/contacts/times/states`); `SCORE_RADIUS` value; the `dt > 2e-3` tunnel guard; 2D loop order (RK4→peak→plane_h→board→rim→score→landing) which must stay identical to `basketball_shot_2d.simulate`.
- **experiment.py**: CSV column order + metadata keys (test_experiment asserts them); grid defaults; `JITTER_*`; `batch_simulate` return `(made,swish,rim_in,board_in)`; `SCORE_RADIUS` must equal simulation's. **Do NOT** change the inline batch collision without resolving §3(b) below.
- **validation.py**: `REQUIRED_FIELDS`; label sets; binary vs multiclass handling; metric formulas (Wilson/kappa/MCC) — DATA_SPECIFICATION.md §3 is the contract.
- **plotting.py / make_interactive.py**: plot geometry, outcome color map, `OUTCOME_COLORS/LABELS`.
- **basketball_shot_2d.py**: treat as the frozen 2D reference; any change must keep 6/6 `--check` and library-2D equivalence.
- **data_prep.py**: documented constants (51° fallback; backspin 14.137167 rad/s = 2.25 RPS; standing-reach 1.33; jump 0.41–0.50 → half-jump; `release_x = −0.375 − distance`) — cited across 4 docs.
- **extract.py**: `FEET_TO_METERS=0.3048`; moment indices `[1]/[3]/[5]`; entity x/y/z at `[2]/[3]/[4]`; `COLUMNS` order.

Known intentional differences — do NOT "fix" (already documented as separate conventions): FREE_THROW 4.60 (docs) vs 4.57 (code), backspin 23 (experiment) vs 14.137167 (data_prep), 3D vs 2D constant sets, `ideal_parabola` hardcoded `0.10` (basketball_shot_2d) vs `RELEASE_FLOOR_2D` (physics) — same value, cosmetic only.

### §3(b) batch-vs-scalar collision divergence (report, don't silently change)
`experiment.batch_simulate` (lines ~192-211) inlines collision instead of calling `collision.resolve_contacts`. It: uses a single `RESTITUTION` (ignores `RIM_RESTITUTION`), selects `board` normal with board-priority via `np.where`, applies `v − (1+e)·vn·n` (normal-only, tangent implicitly retained 1.0), and does one-pass position push (no 4-iteration best-candidate). `simulation.simulate_shot` uses `resolve_contacts` (per-surface restitution, bounded multi-pass). With current defaults (both e=0.7) single-surface results agree, but multi-contact (board+rim near the joint) and any future `RIM_RESTITUTION` change will diverge. Verify with a same-input comparison and report; a real fix is cross-file (experiment + collision) and is the integrator's call.

## 4. Numeric baseline probe protocol (mandatory before/after every edit)

Capture BEFORE, re-run AFTER, put both numbers in the report; any drift must be explained or reverted. Probes (all deterministic, <60 s, no matplotlib):
1. 3D shot outcome: `simulation.simulate_shot([-4.57,2,0], release_velocity(7.5,51), 23)['outcome']` → expect `swish`; also record final `states[-1]` (6 values) and `reason`.
2. Trajectory endpoint: `physics.integrate([-4.6,2,0], release_velocity(7.1,51), 23, t_max=2.0)` → last x,y,z and landing t (compare physics.md §8.2 nominal ≈ x=+1.313, no-collision self-test).
3. Forces: `drag_force([7,2,-1])` (dot(v,fd)<0, scales ×4 when v doubled); `magnus_force([7,1,0], spin_vector(23))` → fy>0.
4. Collision: `reflect([5,-2,0],[-1,0,0],0.7)` → `[-3.5,-2,0]`; `detect_backboard([-0.05,3.2,0])` → penetration≈0.07, normal `[-1,0,0]`; `detect_rim([RIM_CENTER[0]+0.15,3.05,0])` is not None.
5. 2D: `simulation.simulate_2d(2.0,51,23,7.9,4.6)['outcome']` → `SWISH`; all 6 scenes from `simulation.__main__`/`basketball_shot_2d.DEMO_SCENES`; `physics.acceleration_2d(7,0,23*sin(radians(51)),air=True)` record (ax,ay) sign.
6. Sweep (small): `experiment.batch_simulate` on 2-3 shots vs scalar `simulate_shot` same inputs; `batch_simulate_2d(2.0,[51,51],[23,23],[7.9,7.9],4.6)`.
7. validation: `wilson_ci(154,305)` sanity + `_to_binary`/`_canonical` label mapping for all documented labels.

Report table: probe | input | before | after | note.

## 5. Per-file prioritized checklist (look here first)

- **physics.py** — (1) 2D Magnus sign vs §1/§2-2; (2) `acceleration_batch` vs `acceleration` scalar equivalence; (3) `integrate` landing interpolation guard (`denom==0`); (4) 2D degenerate-input guards (`ideal_arc_coeffs_2d`/`vacuum_aim_2d`/`ideal_parabola_2d`) still cover v=0/θ=90°/h0-below-plane.
- **collision.py** — (1) `reflect` normal/tangent decomposition + copy-on-separating; (2) `_detect_*_valid` nearest-point geometry (edge/corner, axis degenerate direction); (3) `resolve_contacts` iteration bounds + "restitution once" logic; (4) 2D `detect_scoring_cross_2d` margin-window guard + `cross_board_plane_2d` NaN guard.
- **simulation.py** — (1) 3D scoring/landing interpolation frac guards; (2) collision contact recording (`incoming_kinds` vs `has_hit_*`) vs docstring; (3) 2D loop order & margin pre-check vs `basketball_shot_2d.simulate`; (4) `fit_segments_2d` degenerate-x guard.
- **experiment.py** — (1) `batch_simulate` inline collision vs `resolve_contacts` (§3b); (2) `_write_grid_atomic`/`_write_csv_atomic` shape & column checks; (3) `band_from_flags` midpoint rule vs doc; (4) 2D batch board/rim ordering vs `simulate_2d`.
- **validation.py** — (1) `wilson_ci` edge cases (n=0, k out of range, z≤0); (2) label normalization (`_to_binary`/`_canonical`) vs DATA_SPECIFICATION §3.3; (3) confusion-matrix / per-class metric denominators (zero guards); (4) `make_dummy_data` correlated self-consistency.
- **plotting.py** (static + py_compile + in-process matplotlib stub if needed) — (1) `vacuum_launch_angle`/`vacuum_trajectory`/`interp_y_at_x` degenerate guards; (2) `_read_sweep` grid-order & [0,1] checks; (3) `plot_free_vs_three` distance-sign fix (abs).
- **make_interactive.py** (static + py_compile; plotly absent) — (1) `compute_trajectory` downsample/pos/speed guards; (2) outcome color/label fallback for unknown strings; (3) `enhance_html` anchor injection (no-op on missing anchors).
- **basketball_shot_2d.py** (static + py_compile; TkAgg absent) — (1) `dv`/`simulate` Magnus sign + loop order vs library 2D layer; (2) `ideal_parabola` v=0/θ=90° guards; (3) `find_band` midpoint rule vs `experiment.find_band_2d`; (4) `fit_segments` degenerate-x branch.
- **data_validation/data_prep.py** — (1) `_initial_velocity` 51° fallback formula + denominator guard (matches DATA_SPECIFICATION §7); (2) `_estimate_release_height` constants; (3) `_unit_scale`/header-normalisation aliasing; (4) `_read_rows` speed/angle pair-required check + `None`-in-row handling.
- **data_validation/extract.py** — (1) `extract_ball_rows` index `[2]/[3]/[4]` + short-frame skip; (2) `FEET_TO_METERS` + rounding; (3) `selfcheck` fixture expected values.
- **test_core.py / test_collision.py / test_experiment.py / test_data_prep.py** — read-only; if a test asserts wrong behaviour, report with evidence, do NOT edit. (See caveats below.)

## 6. Test-file & environment caveats (report, do NOT edit)

- **test_data_prep.py**: has NO `if __name__ == "__main__"` block → `python test_data_prep.py` **runs zero tests** (silent exit 0). Two `ReleaseHeightTests` methods reference an undefined name `prep` (lines 29, 35). Exercise it via `python -m unittest test_data_prep`; expect `NameError` on those two (pre-existing test defect to REPORT, not fix).
- **test_experiment.py**: 8 tests run; the 2 `TemporaryDirectory` cleanup `PermissionError`s are a sandbox artifact — do NOT touch.
- **plotting.py / make_interactive.py**: matplotlib/plotly not installed and uninstallable. Audit statically + `python -m py_compile`; to execute pure logic inject in-process stubs (`sys.modules["matplotlib"]=types.ModuleType(...)` with `.use`, and `sys.modules["matplotlib.pyplot"]=stub`), never add stub files to the repo.
- Encoding: every file is UTF-8 with Chinese comments. Use the repo read/grep tools (never PowerShell `Get-Content`, which decodes GBK and garbles). Use the `edit` tool for surgical changes; never corrupt Chinese text, BOM, or line endings.

## 7. Verification commands (run what applies to the touched file)

```
python test_core.py            # 13/13 baseline
python test_collision.py       # 24/24 baseline
python -m unittest test_data_prep   # actually runs data_prep tests (see caveat)
python -m unittest test_experiment  # informational only (temp cleanup artifact)
python -m py_compile <file.py>      # for matplotlib/plotly-dependent files
python -c "import <module>"         # import sanity
python physics.py ; python collision.py ; python simulation.py   # self-checks
python basketball_shot_2d.py --check    # 6/6 2D scenes
```
Keep runs light: small grids only, never the interactive demo, no git/pip, no `.csv/.png/.md` edits.
