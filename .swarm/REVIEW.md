# Adversarial review — all repairs (COMP1110 basketball shot simulator)

Reviewer pass over the complete change set produced by `fix-physics`, `fix-collision`,
`fix-simulation`, `fix-experiment`, `fix-validation`, `fix-demo2d`, `fix-viz`,
`fix-data-validation`. This is an independent, adversarial read: every hunk was
checked against the ground-truth docs, re-run, and numeric-stability-compared
against `git show HEAD:<file>` reconstructions.

**Bottom line: no fix is wrong. All five edited files are FIXED-CORRECTLY or
(where noted) an acceptable defensive narrowing. The run should NOT be blocked.**
There are follow-ups for the integrator, and one test-file defect that was never a
builders' job to fix (read-only) but must be reported.

---

## 1. Change set under review

`git diff --stat` (5 files, +55 / −35):

```
basketball_shot_2d.py   |  3 +++
data_validation/data_prep.py | 13 ++++---------
experiment.py           | 26 ++++++++++++++++++--------
physics.py              |  9 ++++++++-
validation.py           | 39 ++++++++++++++++++++++-----------------
```

Nothing else was touched. `git status` shows only these five `.py` files modified,
plus the swarm bookkeeping dirs (`.swarm/`, `.dsh-swarm/`). No `.md`, `.csv`, `.png`,
or `test_*.py` was edited. No new dependency was introduced.

---

## 2. Per-hunk verdict

### 2.1 `physics.py` — `ideal_arc_coeffs_2d` (lines 387–390)

- **Old**: `return math.tan(th), G_2D / (2.0 * v * v * c * c)`.
- **New**: computes `denom = 2.0 * v * v * c * c` and raises
  `ValueError` when `denom == 0.0`.

**Is the old code wrong?** Yes. `ideal_arc_coeffs_2d(2.0, 51.0, 1e-200)` raised
`ZeroDivisionError` because `v*v` underflows to `0.0` and the code divided by it.
This contradicts the module docstring (physics.py:8–9) and the function docstring
(physics.py:376–377) that promise a clean `ValueError` for the degenerate-input
family instead of a crash. Reproduced on the HEAD tree: `ZeroDivisionError`.

**Is the new code right?** Yes for the reported case: the guard is an exact
`denom == 0.0` float check, hit precisely when `v*v` (or `c*c`) underflows with
`v > 0`, and it raises the documented clean error. No false positive: `v <= 0` is
already rejected earlier (line 381), and `abs(c) >= 1e-12` is guaranteed, so the
only way `denom == 0.0` is underflow. Normal inputs are untouched (verified below).

- **Residual note (not a blocker)**: `denom == 0.0` catches underflow-to-zero but
  not the subnormal band where `v*v` is nonzero yet `G_2D/denom` overflows to `inf`
  (v ≈ 1e-160). That is physically meaningless and out of scope; recorded for
  completeness only.

**Verdict: FIXED-CORRECTLY.**

### 2.2 `physics.py` — `ideal_parabola_2d` (lines 418–421)

- **New**: after computing `x_land`, raises `ValueError("no positive landing root …")`
  when `x_land <= 0.0`.

**Is the old code wrong?** Yes. The function docstring (physics.py:402–403) already
promised "从落地平面以下出手且仰角向下打不出正根 … 显式报错", but the code only
guarded `disc < 0`, so the below-floor + downward-angle case returned a **negative**
`x_land` and then `np.linspace(0.0, x_land, n)` silently produced a **descending**
x-grid (garbage). This is the "degenerate-input → nonsense instead of documented
error" class. Reproduced on HEAD: `ideal_parabola_2d(0.05, -30, 7.0)` returned
`x_land < 0`.

**Is the new code right?** Yes, and with no false positive. `x_land = (slope + sqrt(disc))/(2a2)`
with `a2 > 0` (already enforced). `x_land <= 0` iff `slope < 0` **and** `b = h0 − RELEASE_FLOOR_2D < 0`
(if `b >= 0`, `disc >= slope²` so `slope + sqrt(disc) >= 0`). That is exactly the
"below floor + downward" degenerate case the docstring names. Upward shots from below
floor (`slope > 0`) still land forward and are not rejected.

**Verdict: FIXED-CORRECTLY.**

### 2.3 `basketball_shot_2d.py` — `fit_segments` (lines 224–226)

- **New**: `if xs[-1] - xs[0] < 1e-9: continue` after the x-monotonic flip.

**Is the old code wrong?** Yes — this is drifted duplicate logic. The library
`simulation.fit_segments_2d` (simulation.py:427–429) already has the identical guard
and skips a near-constant-x segment (where `np.polyfit(xs, ys, 2)` is ill-conditioned
and returns garbage coefficients + `RankWarning`); the standalone copy lacked it.
Verified: with a matplotlib stub, `demo.fit_segments` and `simulation.fit_segments_2d`
now return bit-identical results on both a normal segment (1 seg, identical coeffs)
and a near-constant-x segment (0 segs, both skip).

**Is the new code right?** Yes — the guard is verbatim the library's, placed after
the flip (so `xs[-1] >= xs[0]`), threshold `1e-9` identical. It is a strict no-op for
every segment with meaningful x-span, so normal trajectories are unchanged.

**Verdict: FIXED-CORRECTLY.**

### 2.4 `experiment.py` — `run_sweep_2d` (lines 785–795)

- **Old**: built `vs` from `speeds` or `np.linspace(v_lo, v_hi, int(n_speed))`, then
  checked `vs.size == 0`, finite-ness, and finally `int(n_speed) < 2` **unconditionally**.
- **New**: validates `n_speed` only when `speeds is None`; when `speeds` is given,
  requires `vs.size >= 2`; finite-ness is checked for both.

**Is the old code wrong?** Yes, two ways. (a) `run_sweep_2d(speeds=[6,7,8], n_speed=1)`
raised `ValueError: n_speed must be >= 2, got 1` even though `n_speed` is ignored when
`speeds` is explicit — a spurious error. (b) a 1-element `speeds` array slipped through
(only `size == 0` was rejected), which downstream `band_from_flags`/window logic cannot
meaningfully handle. Reproduced on HEAD: the `n_speed=1` case raised; the `size==1`
case ran unguarded.

**Is the new code right?** Yes. The effective speed grid (the thing actually used) is
now validated, `n_speed` is checked only in the branch that uses it, and `>= 2` is the
correct minimum for a "widest made-speed window" scan. Finite-ness is still enforced
for both branches. Confirmed on current: `speeds=[6,7,8], n_speed=1` runs; `speeds=[7.0]`
raises `ValueError: speeds must contain at least 2 values, got 1`.

**Verdict: FIXED-CORRECTLY.**

### 2.5 `experiment.py` — `run_sweep_mp` (lines 411–418)

- **New**: `release_pos` finite check, `speed = float(speed)` finite-positive check,
  and `int(JITTER_SHOTS) > 0` check, all before `ProcessPoolExecutor`.

**Is the old code wrong?** Partially. `run_sweep_mp` previously only checked
`release_pos.shape`; a `NaN`/non-finite `release_pos` or a `NaN`/`<=0` `speed` would
have silently propagated into the child workers and into the output `data.csv`
("silent NaN" class). Adding the finite/positive guards closes that. This mirrors the
guards `run_sweep` already had (lines 328–334).

**Is the new code right?** Yes, with one caveat: the `int(JITTER_SHOTS) > 0` check is
**dead code** — `JITTER_SHOTS` is a module constant (`= 100`), not a parameter, so the
condition is always false. It is harmless and merely mirrors the equally-dead check in
`run_sweep` (line 333), but it is "speculative/consistency" hardening rather than a
demonstrated reachable defect. No signature or default changed; no drift (verified: the
3×3 sweep output is byte-identical pre/post).

**Verdict: ACCEPTABLE (defensible NaN guard + one dead-code line; not a blocker).**

### 2.6 `validation.py` — `run_validation` (lines 190–250)

- **Old**: on `predict()` raising `ValueError`, set `pred_bin = "miss"`, so an
  error row whose `actual_outcome` was `miss` counted as a **true-negative agreement**.
- **New**: `pred_bin = None` for errors; `match` is then always `False`; the 2×2 matrix
  (`tp/fp/fn/tn`) and multiclass `cm` are updated only `if pred_bin is not None`; and
  `p_actual_made` is now `n_actual_made / n` (a direct count) instead of `(tp + fn) / n`.

**Is the old code wrong?** Yes — a doc-vs-code contradiction. The module docstring
(validation.py:8–10) and DATA_SPECIFICATION.md §3.4 both state that invalid-parameter
rows "count as binary disagreement" and are omitted from the multiclass matrix, yet the
old code made `error + actual miss` an *agreement* and a `tn`, inflating agreement rate
and specificity. (For `actual made + error` it correctly produced `fn` only by accident
of the "miss" sentinel.)

**Is the new code right?** Yes and internally consistent. `pred_bin=None` can never equal
`"made"`/`"miss"`, so error rows are always disagreement and never enter a confusion cell.
Because error rows no longer contribute to `fn`, the direct `n_actual_made` count is the
correct `p_actual_made` (this is the necessary companion change — without it the made
rate would under-count). The `cm`/`mc_used` behaviour is unchanged (error rows were
already excluded because `_canonical("error")` is `None`). The no-error path is
bit-identical (verified below). Reproduced on current: a 2-shot file (1 invalid y<0 with
`actual=miss`, 1 valid made) now yields agreement 0/2 and `tp/fp/fn/tn = 0/0/0/0`
(previously the invalid-miss row was a `tn`).

**Verdict: FIXED-CORRECTLY.**

### 2.7 `data_validation/data_prep.py` — `_map_outcome` (lines 94–95)

- **New**: adds `rim-in`, `board-in`, `bounce-in` to the made set.

**Is the old code wrong?** Yes. DATA_SPECIFICATION.md §3.3 lists these three as made
labels, and `validation._MADE_LABELS` (validation.py:36) accepts them, so a raw source
value of `rim-in`/`board-in`/`bounce-in` was rejected with "unrecognized outcome".
Reproduced: `_map_outcome('rim-in',1)` raised; now returns `"made"`.

**Verdict: FIXED-CORRECTLY.**

### 2.8 `data_validation/data_prep.py` — `_read_rows` outcome alias (line 186)

- **Old**: alias set contained `"madeshots"`; **new**: `"madeshot"`.

**Is the old code wrong?** Yes. DATA_SPECIFICATION.md §7 names the recognized binary
column `made_shot` (singular), whose normalised form is `madeshot`. The old alias
`madeshots` could only match a literal `made_shots`/`made shots` header, so the
documented `made_shot` column was not recognised (`_find_column` raised). Reproduced.

**Verdict: FIXED-CORRECTLY.** (Note: a literal plural `made_shots` header is no longer
matched, but that header is not documented and was never correct.)

### 2.9 `data_validation/data_prep.py` — `_unit_scale` (line 75)

- **Old**: `any(unit in name for unit in ("inch", "_in", "(in)"))`.
- **New**: `any(unit in name for unit in ("inch", "(in)")) or name.endswith("_in")`.

**Is the old code wrong?** In principle, yes: the `"_in"` *substring* misreads the
English preposition "in" (e.g. `Distance_in_m`) as inches and returns `0.0254`. The new
form treats `_in` as inches only as a suffix, which is a **strict narrowing** — every
legitimate inch header (containing `inch`/`(in)`, or ending in `_in`) still maps to
`0.0254`, so there is no regression. Verified: `_unit_scale('release_height_in')` and
`('release_height_inches')` still → `0.0254`; `('Distance_in_m')` now → `1.0`.

**Caveat (honesty note, not a blocker):** reachability of the specific false positive is
limited — the distance/height/player-height headers are already constrained by the
column-finder aliases, so a raw `Distance_in_m` header would fail `_find_column` before
reaching `_unit_scale`. This change is therefore defensive hardening (aligned with §7's
"unit **suffixes**" wording) more than a demonstrated reachable bug. It is safe and
correct, so it stands.

**Verdict: ACCEPTABLE (safe defensive narrowing; no regression).**

### 2.10 `data_validation/data_prep.py` — `_read_rows` speed/angle check removed (was lines 234–239)

- **Old**: raised `ValueError` when exactly one of `speed_column` / `release_angle_column`
  was present.
- **New**: check removed; the downstream `if speed_column and release_angle_column:` else
  `_initial_velocity(...)` fallback handles it.

**Is the old code wrong?** Yes. DATA_SPECIFICATION.md §7 (and the module docstring) say
"when both are present → use speed+angle; **otherwise / if either is absent → 51° vacuum
fallback**". The old guard raised instead of falling back when exactly one was present —
a doc-vs-code contradiction. The new code matches the doc: both → measured components,
otherwise → fallback.

**Verdict: FIXED-CORRECTLY.**

---

## 3. Hard-rule / scope-discipline checks

| Check | Result |
|---|---|
| Public signature / name / default / parameter change | **None.** All hunks are internal guards or internal logic; no function signature, class, parameter name, or default changed. |
| Doc / data / `.md` / `.csv` / `.png` edit | **None.** |
| Test edited to pass | **None.** `test_*.py` untouched (confirmed via `git status` + `git diff`). |
| New dependency | **None.** |
| Debug print left behind | **None.** (No new `print` in any hunk.) |
| Unused import left behind | **None.** |
| Dead code left behind | One line: the `int(JITTER_SHOTS) > 0` check in `run_sweep_mp` (a module constant, always false) — mirrors the pre-existing dead check in `run_sweep`. Cosmetic, not a blocker. |
| Cross-file change by a builder | **None.** Each builder stayed within its own file. |

---

## 4. Test re-run (independent)

| Command | Result |
|---|---|
| `python test_core.py` | **13/13 PASS** |
| `python test_collision.py` | **24/24 OK** |
| `python -m unittest test_data_prep` | 3 pass + **4 pre-existing `NameError: name 'prep' is not defined`** (see §6.1) |
| `python test_data_prep.py` | exits 0 but **runs zero tests** (no `__main__` block) — see §6.1 |
| `python test_experiment.py` | 8 ran, **2 errors only** — both `tempfile.TemporaryDirectory` cleanup `PermissionError` on chmod (the documented sandbox artifact). **No new error.** |
| `python -m py_compile` (all 10 in-scope .py) | blocked writing `__pycache__` (sandbox); replaced by `ast.parse` over all 10 files → **syntax OK**, plus all modules import cleanly. |
| `python basketball_shot_2d.py --check` | cannot run: `import matplotlib` fails (matplotlib not installed — documented). Verified `fit_segments` via in-process matplotlib stub instead (see §2.3). |

---

## 5. Numeric stability (independent)

Reconstructed the pre-edit files with `git show HEAD:<file>` into the OS temp dir and
ran an identical 51-key probe against HEAD and current (physics 2D arc/parabola on four
normal `(h0, angle, v)` inputs; a 3D `simulate_shot` outcome + final state; two
`collision.reflect` results; a small `run_sweep_2d` CSV; validation label maps +
`wilson_ci` + a 6-shot no-error `run_validation` metrics).

**Result: 51/51 keys identical — zero drift on normal inputs.** The only intended
differences are the degenerate inputs listed in §2, each now producing a clean
`ValueError`/`"made"`/`1.0` instead of a crash/garbage/spurious error:

| Probe (degenerate input) | HEAD (old) | Current (new) |
|---|---|---|
| `ideal_arc_coeffs_2d(2.0, 51.0, 1e-200)` | `ZeroDivisionError` | `ValueError` |
| `ideal_parabola_2d(0.05, -30, 7.0)` | negative `x_land`, descending linspace | `ValueError` |
| `run_sweep_2d(speeds=[6,7,8], n_speed=1)` | `ValueError: n_speed must be >= 2` | runs OK |
| `run_sweep_2d(speeds=[7.0])` | ran unguarded (size 1) | `ValueError: …at least 2 values` |
| `_map_outcome('rim-in'|'board-in'|'bounce-in')` | `ValueError` | `"made"` |
| `_find_column(['made_shot',…])` | `ValueError` | `"made_shot"` |
| `_unit_scale('Distance_in_m')` | `0.0254` (wrong) | `1.0` |
| `_unit_scale('release_height_in')` | `0.0254` | `0.0254` (unchanged) |

---

## 6. Defects the builders MISSED (report-only / follow-ups)

### 6.1 `test_data_prep.py` — broken test harness (pre-existing, read-only, MUST REPORT)

- `test_data_prep.py:29` and `:35` reference an undefined name `prep`
  (`prep._estimate_release_height(...)`), but the file only does
  `from data_validation.data_prep import _estimate_release_height, _velocity_from_speed_and_angle`
  (line 24) — no `import ... as prep`. Running via `python -m unittest test_data_prep`
  → 4 `NameError`.
- The file has **no `if __name__ == "__main__": unittest.main()`** block, so
  `python test_data_prep.py` exits 0 **without running any test**. This is why the
  dispatch baseline recorded `python test_data_prep.py` as "OK" — that "OK" is
  misleading; the data-prep suite currently executes **zero** tests.
- Already flagged by `plan-audit` (§6 of PLAN.md). It is a **test-file defect, read-only
  for builders** — the correct action is to report it (as here), not edit the test.

### 6.2 `plotting.py` `vacuum_launch_angle` — `dx = 0` → silent NaN (missed by `fix-viz`)

- `plotting.py:239` `dx = x1 - x0`; line 241 `a = 0.5 * G * dx**2 / v**2`; line 247
  `u = (-b + np.sqrt(disc)) / (2.0 * a)`. With `dx == 0` (shooter at the rim-centre x),
  `a == 0` and `u` becomes `0/0` → `nan` (verified: returns `nan` with
  "invalid value encountered in scalar divide"). This is the "silent NaN propagation"
  class (rule 5) — the function should raise a clean error (e.g. `dx == 0`), consistent
  with its own docstring's `v <= 0 → ValueError` convention.
- `fix-viz` noticed this but classified it "non-blocking observation"; it is a real (if
  low-severity) missed defect and a legitimate small follow-up.

### 6.3 2D Magnus sign ambiguity — cross-file, doc self-contradictory (reported, not fixed)

- `physics.acceleration_2d` (physics.py:342–343) computes Magnus =
  `(+BM·ωz·vy, −BM·ωz·vx)` = **−(ω×v)**, which for backspin (`ωz>0`, `vx>0`) gives
  **downward** `ay`, contradicting the 3D `magnus_force` (+ω×v, upward) and
  SIMULATION_2D_PHYSICS.md §7 "力 ∝ ω×v" / §3 "后旋→升力向上". The §3 formula text
  matches the code, so the doc is **self-contradictory**; the sign is duplicated in
  `basketball_shot_2d.py dv()` and `experiment._dv2`. Correctly **not** silently flipped.
  This is the integrator's cross-file decision (PLAN §1 highest-value item).

### 6.4 `experiment.batch_simulate` inline collision vs `collision.resolve_contacts` — cross-file latent drift (reported, not fixed)

- `experiment.batch_simulate` inlines a single-restitution, normal-only, one-pass
  collision instead of calling `collision.resolve_contacts` (per-surface restitution,
  bounded multi-pass). Agrees today only because both restitution constants are 0.7 and
  single-surface; multi-contact (board+rim near the joint) and any future
  `RIM_RESTITUTION` change diverge. Cross-file, integrator's call (PLAN §3b).

---

## 7. Per-file verdict table

| File | Changed? | Verdict |
|---|---|---|
| `physics.py` | yes (2 guards) | **FIXED-CORRECTLY** |
| `collision.py` | no | **CLEAN** (builder correctly found nothing; my re-run of 24/24 + probe agrees) |
| `simulation.py` | no | **CLEAN** |
| `experiment.py` | yes (2 guards) | **FIXED-CORRECTLY** (`run_sweep_2d`) / **ACCEPTABLE** (`run_sweep_mp`, one dead-code line) |
| `validation.py` | yes (1 fix) | **FIXED-CORRECTLY** |
| `basketball_shot_2d.py` | yes (1 guard) | **FIXED-CORRECTLY** |
| `plotting.py` | no | **CLEAN** (but see §6.2 — one missed low-severity defect) |
| `make_interactive.py` | no | **CLEAN** |
| `data_validation/data_prep.py` | yes (4 fixes) | **FIXED-CORRECTLY** (3) / **ACCEPTABLE** (`_unit_scale`, defensive narrowing) |
| `data_validation/extract.py` | no | **CLEAN** |

No file is **NEEDS-REDO**. No fix is wrong.

---

## 8. Required follow-ups for the integrator (numbered)

1. **`test_data_prep.py`** — report the harness defect (undefined `prep` at lines 29 &
   35; no `unittest.main()` block → `python test_data_prep.py` runs zero tests). Tests
   are read-only for builders, so this is a human/integrator-level report, not an edit
   inside the run. Suggested minimal fix (for the human, outside builder scope): add
   `import data_validation.data_prep as prep` and an `if __name__ == "__main__": unittest.main()`.
2. **`plotting.py:239-247`** — `vacuum_launch_angle` `dx == 0` → `0/0` → `nan`. Add a
   clean `ValueError` for `dx == 0` (or `abs(dx) < eps`) before the division, matching
   the function's documented degenerate-input convention. Low severity.
3. **2D Magnus sign** (physics.py:342–343 + basketball_shot_2d.py `dv` + experiment.py
   `_dv2`) — resolve the doc-vs-code-vs-3D sign contradiction as one decision across all
   three files (do NOT flip unilaterally). SIMULATION_2D_PHYSICS.md §3 is self-contradictory.
4. **`experiment.batch_simulate` inline collision vs `collision.resolve_contacts`** —
   either route the batch path through `resolve_contacts` or document the divergence as
   intentional; verify a board+rim multi-contact case before/after.
5. **(Optional, cosmetic)** remove the dead `int(JITTER_SHOTS) > 0` check in
   `run_sweep_mp` (and ideally `run_sweep`) — it guards a module constant. Not required
   for correctness.
