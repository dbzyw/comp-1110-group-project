# Data Specification for the Basketball Shot Validation Pipeline

## 1. Purpose

This document defines the input contract implemented by the project's `validation.py`, describes the data files currently kept in this folder, and records the limits of using those files for model validation.

Validation compares recorded outcomes against the frozen 3D physics simulation. Data is for evaluation only; it must not be used to tune model constants. The simulation uses SI units and a right-handed coordinate system:

- `x`: horizontal, from shooter towards basket
- `y`: vertical, positive upwards
- `z`: lateral
- Pure backspin: angular velocity vector `(0, 0, +backspin)` in rad/s

## Table of contents

1. Purpose · 2. Files in this folder · 3. Exact input contract · 4. Tracking extraction output · 5. Selected initial-conditions CSV · 6. Preparation requirements · 7. `data_prep.py` assumptions and usage · 8. Readiness of current data · 附录 A/B（复验数据、复算命令）

## 2. Files in this folder

| File | Observed contents (re-checked 2026-10-21) | Relevance to `validation.py` |
|---|---|---|
| `extracted_ball_tracks.csv` | 24,073 tracking rows, 6 columns; 49 distinct event IDs (1–54); 10 complete duplicate rows; 953 blank `shot_clock` | Frame-level positions only; it does not directly contain shot-level release inputs or outcomes. |
| `selected_shot_initial_conditions.csv` | Five rows `x_m,y_m,z_m,v0x,v0y,v0z` | Supplies the first five tentative 3D records; it lacks source shot IDs, backspin, outcome labels, and confirmed coordinate/unit metadata. |
| `filtered_data_30_groups.csv` | 30 rows, columns `x_m,y_m,z_m,v0x,v0y,v0z` | Supplies the other 30 tentative 3D records. Source axes and units remain unverified. |
| `basketball_shooting_dataset.csv` | 300 rows × 20 columns (e.g. `Player_ID`, `Distance_from_Basket_m`, `Shot_Result`, `Shot_Speed_m_s`, `Release_Angle_deg`, gyroscope `*_deg_s`); binary outcomes 148 made / 152 miss | Raw shot-level source CSV; input to `data_prep.py`. Its distance and outcome columns are recognised by the helper; provenance/axes still unconfirmed. |
| `data_prep.py` | Conversion helper (not data) | Applies the §7 straight-on assumptions to turn the raw dataset into `valid_data_2D.csv`. |
| `valid_data_2D.csv` | 300 rows, exact nine-column schema; IDs 1–300; 148 `made` / 152 `miss`; `release_z = v0z = 0`; imputed `backspin = 14.137167 rad/s` | A 2D/straight-on approximation that can be parsed by `validation.py`; it is not measured 3D kinematics. |
| `valid_data_3D.csv` | 35 rows, exact nine-column schema; IDs 301–335; all labels assumed `made`; imputed `backspin = 14.137167 rad/s` | Tentative 3D inputs with supplied position and velocity components. Source axes, origin, velocity units, and labels remain unverified. |
| `export_blender_3d.py` | Export helper | Simulates a validation CSV and creates a 60 fps Blender-ready trajectory export without changing the three-demo Blender scene. |
| `extract.py` | Extracts ball positions from a local `sample.json` | Writes tracking rows; the expected JSON source is not currently in this folder. |

All data tables use comma-delimited UTF-8 CSV. The original workbook was
converted to `selected_shot_initial_conditions.csv`; it is no longer kept in
this folder. Source provenance and the relationship between the tracking data
and selected initial conditions remain unconfirmed.

## 3. Exact input contract from `validation.py`

### 3.1 Required CSV header

`validation.py` uses `csv.DictReader` and requires every field below to be present. Keep this spelling and order in validation files:

```csv
shot_id,release_x,release_y,release_z,v0x,v0y,v0z,backspin,actual_outcome
```

The loader checks that the required column names are present; it does not
require these to be the only columns. It expects one record per shot.

### 3.2 Field types and meanings

| Field | Code-level requirement | Meaning and units |
|---|---|---|
| `shot_id` | Must parse with Python `int()` | Integer shot identifier. Despite any more general description elsewhere, the current loader does not accept IDs such as `source_row_0001`. Duplicate IDs generate a warning but are still included. |
| `release_x` | Finite float | Ball-centre release x coordinate, metres. The shooter is on the negative-x side; the ball travels toward the basket in the positive-x direction. |
| `release_y` | Finite float | Ball-centre release height, metres, positive upwards. The simulation rejects values below zero. |
| `release_z` | Finite float | Ball-centre lateral release coordinate, metres. |
| `v0x` | Finite float | Initial velocity along x, m/s. |
| `v0y` | Finite float | Initial vertical velocity, m/s. |
| `v0z` | Finite float | Initial lateral velocity, m/s. |
| `backspin` | Finite float | Backspin rate, rad/s. The model maps this to `(0, 0, +backspin)`; positive values give upward Magnus lift for forward-moving shots. |
| `actual_outcome` | Case-insensitive recognized string | Observed result; see supported labels below. |

The loader converts the seven physical values to floats and rejects non-numeric
or non-finite values (`NaN`, `inf`). A fully blank row is skipped; a
partially-filled row is not skipped and will fail numeric or label validation.
The model receives the position, velocity, and backspin; the loader does not
derive these from other columns.

### 3.3 Supported outcome labels

`validation.py` lowercases and trims outcome labels. The accepted labels are:

- Made: `swish`, `rim-in`, `board-in`, `bounce-in`, `made`, `in`
- Missed: `miss`, `out`, `no`

`swish`, `rim-in`, `board-in`, and `miss` can be represented in the four-class
confusion matrix. `bounce-in`, `made`, and `in` indicate only a binary make;
they are included in made/miss statistics but not the four-class matrix.
Do not invent a detailed made-shot subtype when the observation only says
made.

### 3.4 Prediction and reported statistics

For each valid row, `predict()` calls the 3D `simulate_shot()` with the release
position, velocity, and backspin. Simulation outcomes are `swish`, `rim-in`,
`board-in`, or `miss`.

`run_validation()` reports binary agreement/disagreement, Wilson confidence
interval, precision, recall, specificity, F1, MCC, Cohen's kappa, a
no-information baseline, and a four-class confusion matrix for labels with
sufficient detail. Invalid simulation parameters are handled as per-shot
errors by `run_validation`; they count as binary disagreement and are omitted
from the multi-class matrix. Invalid numeric text or unsupported labels fail
while loading the CSV.

## 4. Tracking extraction output

`extract.py` expects a JSON document with an `events` array. It is now driven
by an argparse CLI (`--json`/`--out`/`--events`/`--ball-entity`), so the input
file name, the number of events, and the ball `entity_id` no longer have to be
hand-edited in source; `--events -1` reads every event. By default it processes
the first 50 events, reads the event ID, timestamp, and shot clock from fixed
positions in each `moment`, selects the entity whose ID is `-1` (the ball),
skips malformed frames that are too short to contain the entity list instead of
crashing, and reads its three position values. It assumes those source
positions are in feet, converts them to metres using `0.3048`, rounds
positions to three decimal places, and writes:

```csv
event_id,timestamp_ms,shot_clock,x_m,y_m,z_m
```

`--selfcheck` runs the same extraction against a built-in two-frame fixture
(12.0 ft/8.0 ft/0.0 ft → 3.658/2.438/0.0 m) and asserts row count, column
order, and unit conversion, so the logic can be verified end-to-end without a
`sample.json` that is not present in this folder. `sample.json` itself must be
supplied externally; `extract.py` does not guess a file name and exits with a
clear error if the input is missing or the JSON fails to parse.

This output is frame-level, not one row per shot. Before using it to derive
release velocities, confirm the source JSON layout, entity ID, source units,
axis meaning, timestamp precision, and event-to-shot mapping. The current
export has a repeated rounded timestamp representation (all 24,073 rows share
the single textual value `1.45196E+12`), so recover precise source times
before estimating velocities or frame intervals. Shot-clock values may be
missing (953 blanks; non-blanks range 0.03–24.0). No position cell is blank;
observed ranges are `x_m` −0.545…30.368, `y_m` −0.258…15.592, `z_m`
0.021…5.217 — descriptive only, these do not establish axis meaning.

## 5. Selected initial-conditions CSV

`selected_shot_initial_conditions.csv` has this header:

```csv
x_m,y_m,z_m,v0x,v0y,v0z
```

It contains five records converted from the former workbook, with blank
worksheet rows omitted. Field names suggest positions in metres and velocity
components, but the velocity units, coordinate axes, source method, and
association with individual shots are not documented. It has no shot ID,
backspin, or observed outcome. The full table:

| # | x_m | y_m | z_m | v0x | v0y | v0z |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 14.207 | 7.718 | 2.534 | 0.5 | 0.2 | 0.5 |
| 2 | 4.492 | 10.833 | 2.559 | 1.55 | 0.05 | 1.525 |
| 3 | 24.363 | 8.565 | 2.64 | 1.75 | 0.1 | 5.275 |
| 4 | 5.665 | 7.731 | 2.505 | 1.175 | 0.45 | 0.121 |
| 5 | 5.599 | 7.73 | 2.593 | 2.8 | 0.225 | 0.131 |

The `x_m`, `y_m`, `z_m` names also do not prove these values use the
simulation axes. If `y_m` were vertical release height, the values (≈7.7–10.8
m) are implausible for a ball centre at release; if `x_m` followed the model
axis, the shooter should be on the **negative**-x side (observed: positive,
and beyond the hoop for rows 1–3). These rows look more like court-origin or
opponent-end coordinates; resolve the source convention before use.

## 6. Preparation requirements before validation

To produce a CSV usable by the current `validation.py`:

1. Establish data provenance, access terms, source units, and source coordinate axes.
2. Define one row per shot and assign a unique integer `shot_id`. Keep a documented mapping from that ID to source event/frame records.
3. Provide ball-centre release coordinates transformed to the model axes and expressed in metres.
4. Provide initial velocity components in the same axes and in metres per second. If deriving them from positions, use ordered samples with verified timestamps and document the estimation method and uncertainty.
5. Provide backspin in rad/s with its sign converted to the model's positive-z convention. Do not use a gyroscope component without verifying sensor orientation, units, calibration, and that it represents ball spin.
6. Annotate the observed outcome using one of the supported labels. Preserve binary-only labels as binary; do not infer contact subtype.
7. Check all required fields, unique IDs, finite numeric values, outcome labels, plausible coordinate ranges, and missing/duplicate records.
8. Keep raw data unchanged and store prepared shot-level data separately. Report sample size, exclusions, label granularity, input derivation, and uncertainty.

The project's planned sources include public anonymised tracking data and
approximately 20–30 group-member free throws filmed at 60 fps. These are
plans, not confirmation of the current files' provenance or completed
empirical validation. For team-member footage, obtain consent, store it
locally, avoid retaining identifying face data, and delete it after the final
report.

## 7. `data_prep.py` assumptions and usage

The helper script is a convenience conversion, not a substitute for verifying
source measurements. Run it from the project root or the `data_validation`
folder after placing the raw CSV beside the script:

```text
python data_validation/data_prep.py
```

By default it reads `basketball_shooting_dataset.csv` from the current
directory or script directory, then writes `data_validation/valid_data_2D.csv`.
An alternate source and output can be supplied:

```text
python data_validation/data_prep.py "path/to/source.csv" --output "path/to/valid_data_2D.csv"
```

| CLI 参数 | 作用 | 缺省 |
|---|---|---|
| （位置参数） | 原始 shooting CSV 路径 | `basketball_shooting_dataset.csv` |
| `--output` | 输出 2D valid CSV | `data_validation/valid_data_2D.csv` |
| 合成参数 | Source `Shot_Speed_m_s` + `Release_Angle_deg` when both are present; otherwise 51° vacuum fallback; backspin 14.137167 rad/s; release-height estimate; legacy `release_x = -0.375 - distance`, `release_z = 0` | — |

It recognizes common distance columns (including `Distance_from_Basket_m`)
and binary outcome columns (including `Shot_Result`, `made_shot`, and
`Shot_Accuracy`). Unit suffixes for metres, centimetres, millimetres, feet,
and inches are converted to metres; a distance header with no recognized unit
is assumed to be metres. A provided release-height value takes precedence. If
it is absent or blank and player height plus shot type are available, the
script inserts an explicitly scenario-based release-height estimate. For the
current dataset it assumes an adult male player, estimates standing fingertip
reach as `1.33 × stature`, subtracts 0.12 m to approximate ball-centre offset,
and adds half the 45.5 cm midpoint of a published general adult male vertical
jump guide for `Jump Shot`, `Layup`, and `Tip-in`; `Set Shot` gets no jump
offset. This is a coarse imputation, not measured reach, jump, or release
height. The reference jump-test values are population guidance, not shot
biomechanics, and the multiplier, ball offset, and half-jump fraction are
explicit modelling assumptions. The source dataset has no sex field; the
adult-male scenario was selected for this conversion and may not describe the
actual players. Unknown shot categories or missing height/type values fail
with a row-specific error rather than silently receiving an estimated value.
If the input has neither a release-height value nor both player height and
shot type, the legacy 2.0 m fallback remains in use. A present release-height
column with no recognized unit is assumed to be metres.

The vertical-jump reference is [Topend Sports' adult vertical-jump norm
guide](https://www.topendsports.com/testing/norms/vertical-jump.htm), which
reports 41–50 cm for adult men and notes its test uses a two-leg jump with full
arm movement. [Ogata et al. (2025)](https://doi.org/10.47206/ijsc.v6i1.496)
analysed standing-reach and jump-reach measures for 1,048 NBA Draft Combine
players; that elite sample supports the relevance of reach/jump measurements
but does not validate this stature multiplier or the shot-specific fraction.

For the generated position, the script assumes the distance is a straight-on
horizontal distance to the rim centre. Its legacy mapping uses
`x = -0.375 m`, so `release_x = -0.375 - distance`; this mapping has not been
verified against the external dataset's coordinate convention. It sets
`release_z = 0`. When both source columns are present, it computes the
straight-on components from the recorded speed and release angle:

```text
v0x = Shot_Speed_m_s cos(Release_Angle_deg)
v0y = Shot_Speed_m_s sin(Release_Angle_deg)
v0z = 0
```

If either source column is absent, the legacy fallback assumes a 51-degree
launch and solves the ideal projectile equation, ignoring drag, Magnus lift,
and collisions:

```text
v² = g d² / [2 cos²(theta) (d tan(theta) - (3.05 - release_y))]
v0x = v cos(theta)
v0y = v sin(theta)
v0z = 0
```

If the fallback distance/height combination has no finite positive solution,
the script uses the requested fallback components `v0x=6`, `v0y=4`, `v0z=0`
(m/s). It assigns the midpoint of a
2.0–2.5 RPS practical target range, `2.25 × 2π = 14.137167 rad/s`, to every
shot. This target is reported by the [Spalding TF DNA app](https://smartbasketball.spalding.com/pages/spin-rate-soft-touch-from-proper-shot-mechanics) for its users; it is
a practical reference, not a measured normal range for this Kaggle dataset or
a universal population norm. The Kaggle CSV does not measure ball spin, and
wrist gyroscope values are not substituted for it. Binary outcomes are
normalized to `made` or `miss`; unknown
labels and missing distances stop conversion with a row-specific error. IDs
are sequential integers starting at 1. The script prints the exact
nine-column header and first five prepared records before writing the output.

These assumptions satisfy the file format and parser requirements, but they
do not make the generated inputs equivalent to measured release positions,
3D velocity vectors, or spin. The current 2D file uses source speed and
release angle, but its source axes and release-angle semantics are
unverified; lateral position and velocity remain assumed zero. Do not
interpret its validation metric as an empirical assessment of the physical
model unless these assumptions have been independently confirmed.

## 8. Readiness of current data

The validation inputs are intentionally split:

- `valid_data_2D.csv` contains IDs 1–300, generated from the external
  shooting dataset under a straight-on assumption. Its release height is
  estimated from stature and shot type, `release_z = v0z = 0`, and the
  release velocity is resolved from source `Shot_Speed_m_s` and
  `Release_Angle_deg`. It has 148 `made` and 152 `miss` labels. The
  `model_validation_results_2D.md` metrics are a historical snapshot from
  before the NBA geometry/ball-parameter alignment and are not current-model
  results; the file remains a 2D approximation, not measured 3D release
  kinematics.
- `valid_data_3D.csv` contains IDs 301–335. Positive source `x_m` was
  negated, `z_m` was tentatively mapped to vertical `release_y`, and `y_m`
  to lateral `release_z`; supplied velocity components were copied unchanged.
  Every row is labelled `made` at the user's direction and uses imputed
  `backspin = 14.137167 rad/s`. Its `model_validation_results_3D.md` metrics
  are likewise a pre-alignment snapshot. The labels, source axes, origin, and
  velocity units are unverified; its lateral positions are large
  (0.658–14.248 m). It is a tentative parser-compatible 3D scenario, not an
  empirical validation dataset.

The tracking extract does not satisfy the validation input contract:

- The tracking extract has no release velocity, backspin, shot-level outcome,
  or confirmed mapping from event IDs to shots.
- It is frame-level rather than shot-level, and its exported timestamps all
  have the same rounded representation. It was not added to either validation
  input file.

Running `data_prep.py` recreates the 2D file. The 3D file is assembled from
the two supplied-component CSVs and its tentative mapping described above.
Parser compatibility is not evidence that assumed or copied inputs represent
measured shot conditions. Metrics that include assumed outcome labels are not
an empirical validation result.

### 8.1 Blender trajectory export

Run the following from the repository root to export every row in
`valid_data_3D.csv`:

```powershell
python data_validation\export_blender_3d.py
```

The command creates `data_validation/blender_3d_validation/` with
`shots.json` and one 60 fps trajectory CSV per shot under `trajectories/`.
Each CSV uses the Blender trajectory columns
`frame,x,y,z,vx,vy,vz`; `shots.json` records the original release values,
predicted outcome, contacts, score frame (or `null` for a miss), and the
relative CSV path. It uses `simulation.simulate_shot()`, so its outcomes are
the same as `validation.py`.

This export is a general input format for a future Blender renderer. The
current `blender_3d/build_blender.py` deliberately remains a three-shot
demonstration renderer and does not load this 35-shot manifest.

## 附录 A · 2026-10-21 复验观察值（本报告内数字的出处）

| 对象 | 复验结果 |
|---|---|
| `extracted_ball_tracks.csv` | 24,073 行；49 个 event_id（min 1 / max 54）；完全重复行 10；`shot_clock` 空值 953；`timestamp_ms` 唯一文本值 `1.45196E+12`；位置无空值；范围 x −0.545…30.368 / y −0.258…15.592 / z 0.021…5.217 |
| `selected_shot_initial_conditions.csv` | 5 行，全表见 §5（v0 值均 2 位小数内、疑似手工圆整） |
| `filtered_data_30_groups.csv` | 30 行，列 `x_m,y_m,z_m,v0x,v0y,v0z`；位置范围 x 1.221…27.358 / y 0.658…14.248 / z 2.462…2.534 |
| `basketball_shooting_dataset.csv` | 300 行 × 20 列；`Shot_Result` 1=148 / 0=152；首行样本 `P001 … 4.39 …`；含 `Timestamp`（日期时间）与三轴陀螺仪 `*_deg_s` |
| `valid_data_2D.csv` | 300 行、九列与 §3.1 一致；IDs 1…300；`release_z` / `v0z` 均为 0；`made` 148 / `miss` 152 |
| `valid_data_3D.csv` | 35 行、九列与 §3.1 一致；IDs 301…335；正 `x_m` 已取负、`y_m`/`z_m` 暂按侧向/竖直映射；全为假设 `made`，源坐标与单位未核实 |

## 附录 B · 复算这些数字的命令

```python
import csv, collections
p = 'data_validation/'
rows = list(csv.reader(open(p+'extracted_ball_tracks.csv', encoding='utf-8-sig')))[1:]
ids  = {int(r[0]) for r in rows}                     # 事件数与范围
dups = sum(c-1 for c in collections.Counter(map(tuple, rows)).values() if c > 1)
blank = sum(1 for r in rows if r[2].strip() == '')   # shot_clock 空值
u_ts  = {r[1] for r in rows}                         # 时间戳唯一值
ds = list(csv.reader(open(p+'basketball_shooting_dataset.csv', encoding='utf-8-sig')))[1:]
vd2 = list(csv.reader(open(p+'valid_data_2D.csv', encoding='utf-8-sig')))[1:]
vd3 = list(csv.reader(open(p+'valid_data_3D.csv', encoding='utf-8-sig')))[1:]
oc2 = collections.Counter(r[8].strip().lower() for r in vd2)
oc3 = collections.Counter(r[8].strip().lower() for r in vd3)
int_ids = all(s.lstrip('-').isdigit() for s in [r[0] for r in vd2 + vd3])
```

数字与本文一致即视为规范未腐坏；任何不一致应先在 main 上重验再修订本文。
