# Data Specification for the Basketball Shot Validation Pipeline

> 这是 `DATA_SPECIFICATION.md` 的改进版（2026-10-21），原版保留在同目录。
> 主要变更：加目录；§2/§4/§5/§8 的"当提供时…"占位措辞改为本仓库当前实际观察到的
> 文件与行数（2026-10-21 逐行复验）；§5 补 selected 5 行全表；§7 补 CLI 参数表；
> 附录 C 给出复算这些统计数字的命令。语义与结论未改动。

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
| `selected_shot_initial_conditions.csv` | Five rows `x_m,y_m,z_m,v0x,v0y,v0z` | Has possible position and velocity components, but lacks shot IDs, backspin, outcome labels, and confirmed coordinate/unit metadata (see §5 and 附录 A for the exact values). |
| `basketball_shooting_dataset.csv` | 300 rows × 20 columns (e.g. `Player_ID`, `Distance_from_Basket_m`, `Shot_Result`, `Shot_Speed_m_s`, `Release_Angle_deg`, gyroscope `*_deg_s`); binary outcomes 148 made / 152 miss | Raw shot-level source CSV; input to `data_prep.py`. Its distance and outcome columns are recognised by the helper; provenance/axes still unconfirmed. |
| `data_prep.py` | Conversion helper (not data) | Applies the §7 assumptions to turn the raw dataset (+ optionally the selected file) into `valid_data.csv`. |
| `valid_data.csv` | 305 rows, exact nine-column schema; IDs 1–305 sequential integers; 153 `made` / 152 `miss`; all rows `backspin = 23.0`; converted rows all `release_y = 2.000000`, speeds 5.84–9.17 m/s | Has the exact validation schema and can be parsed by `validation.py`; its inputs are §7 assumptions, so its agreement numbers are not an empirical model assessment. |
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
| `release_x` | Finite float | Ball-centre release x coordinate, metres, positive toward the basket. |
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

`extract.py` expects a JSON document with an `events` array. It processes the
first 50 events, reads the event ID, timestamp, and shot clock from fixed
positions in each `moment`, selects the entity whose ID is `-1` (commented as
the ball), and reads its three position values. It assumes those source
positions are in feet, converts them to metres using `0.3048`, rounds
positions to three decimal places, and writes:

```csv
event_id,timestamp_ms,shot_clock,x_m,y_m,z_m
```

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
directory or script directory, then writes `data_validation/valid_data.csv`.
An alternate source and output can be supplied:

```text
python data_validation/data_prep.py "path/to/source.csv" --output "path/to/valid_data.csv"
```

To also append records from `selected_shot_initial_conditions.csv`, pass its
path explicitly:

```text
python data_validation/data_prep.py --selected-input data_validation/selected_shot_initial_conditions.csv
```

| CLI 参数 | 作用 | 缺省 |
|---|---|---|
| （位置参数） | 原始 shooting CSV 路径 | `basketball_shooting_dataset.csv` |
| `--output` | 输出 valid CSV | `data_validation/valid_data.csv` |
| `--selected-input` | 追加 selected 初值行 | 不追加 |
| `--selected-outcome` | 追加行的结局标签 | `made` |
| 固定合成参数 | 角度 51°、backspin 23 rad/s、高度缺省 2.0 m、`release_x = -0.375 - distance`、`release_z = 0` | — |

The selected file must have the exact columns `x_m,y_m,z_m,v0x,v0y,v0z`.
Those values are copied directly into the matching validation fields, IDs
continue after the raw dataset's generated IDs, and the selected rows receive
the assumed outcome from `--selected-outcome` (default `made`) and the
configured 23 rad/s backspin. This assumes the selected file's coordinates,
velocity units, and axes already match the simulation; confirm this before
interpreting predictions (`extracted_ball_tracks.csv` was deliberately not
appended; see also §5's implausible values).

It recognizes common distance columns (including `Distance_from_Basket_m`)
and binary outcome columns (including `Shot_Result`, `made_shot`, and
`Shot_Accuracy`). Unit suffixes for metres, centimetres, millimetres, feet,
and inches are converted to metres; a distance header with no recognized unit
is assumed to be metres. If no release-height column is found or its cell is
blank, release height defaults to 2.0 m (the current dataset has `Height_cm`
only — player height, not release height, so all 300 converted rows use
2.0 m). A present release-height column with no recognized unit is assumed
to be metres.

For the generated position, the script assumes the distance is a straight-on
horizontal distance to the rim centre. It uses the model's rim-centre
coordinate `x = -0.375 m`, so `release_x = -0.375 - distance`; it sets
`release_z = 0`. It does not copy a potentially ambiguous raw angle or speed.
Instead it assumes a 51-degree launch and solves the ideal projectile
equation, ignoring drag, Magnus lift, and collisions:

```text
v² = g d² / [2 cos²(theta) (d tan(theta) - (3.05 - release_y))]
v0x = v cos(theta)
v0y = v sin(theta)
v0z = 0
```

If the distance/height combination has no finite positive solution, the
script uses the requested fallback components `v0x=6`, `v0y=4`, `v0z=0`
(m/s) (none triggered in the current file). It assigns `backspin=23 rad/s`
to every shot. Binary outcomes are normalized to `made` or `miss`; unknown
labels and missing distances stop conversion with a row-specific error. IDs
are sequential integers starting at 1. The script prints the exact
nine-column header and first five prepared records before writing the output.

These assumptions satisfy the file format and parser requirements, but they
do not make the generated inputs equivalent to measured release positions,
velocity vectors, or spin. Do not interpret validation metrics based on
assumed inputs as an empirical assessment of the physical model unless the
assumptions have been independently confirmed. In particular: because the
release vector was *solved to pass through the rim under vacuum* at 51°,
the full 3D model (drag + backspin, which lower the arrival height) will
systematically miss many "made" rows that were generated from the same
idealized equation — expect a substantial, assumption-driven disagreement
rate, not a model-quality result, when running `validation.py` on this file.

## 8. Readiness of current data

`valid_data.csv` contains 305 parser-compatible rows: 300 converted from the
external shooting dataset, plus five rows copied from the selected
initial-conditions CSV. IDs are sequential integers from 1 through 305 (复验:
all parse as `int()`, unique ✓; outcome counts 153 `made` / 152 `miss`; every
row `backspin = 23`; first 300 rows all `release_y = 2.0` with
`release_x ∈ [-7.805, -1.535]`, solved speeds 5.84–9.17 m/s). For IDs 301–305,
`actual_outcome` was set to `made` at the user's direction and backspin was
assumed to be 23 rad/s. These labels are assumptions, not verified observed
outcomes. The selected coordinates/velocities were copied using their column
names as if their axes and units match the simulation; their `y_m` values
(approximately 7.7–10.8 m) — and their **positive** `x_m` values (the model
expects the shooter on the negative-x side; rows 1 and 3 even place the
release beyond the hoop) — make that interpretation questionable and should
be resolved before using these records for model assessment.

The tracking extract does not satisfy the validation input contract:

- The tracking extract has no release velocity, backspin, shot-level outcome,
  or confirmed mapping from event IDs to shots.
- It is frame-level rather than shot-level, and its exported timestamps all
  have the same rounded representation. It was not added to `valid_data.csv`.

When rerunning `data_prep.py`, include the `--selected-input` option above to
recreate the five appended rows. Parser compatibility is not evidence that
assumed or copied inputs represent measured shot conditions. Metrics that
include assumed outcome labels are not an empirical validation result.

## 附录 A · 2026-10-21 复验观察值（本报告内数字的出处）

| 对象 | 复验结果 |
|---|---|
| `extracted_ball_tracks.csv` | 24,073 行；49 个 event_id（min 1 / max 54）；完全重复行 10；`shot_clock` 空值 953；`timestamp_ms` 唯一文本值 `1.45196E+12`；位置无空值；范围 x −0.545…30.368 / y −0.258…15.592 / z 0.021…5.217 |
| `selected_shot_initial_conditions.csv` | 5 行，全表见 §5（v0 值均 2 位小数内、疑似手工圆整） |
| `basketball_shooting_dataset.csv` | 300 行 × 20 列；`Shot_Result` 1=148 / 0=152；首行样本 `P001 … 4.39 …`；含 `Timestamp`（日期时间）与三轴陀螺仪 `*_deg_s` |
| `valid_data.csv` | 305 行、九列与 §3.1 逐字一致；IDs 1…305 唯一整数；`backspin` 全 23；前 300 行 `release_y` 全 2.0、`release_x` −7.805…−1.535、合成速率 5.84…9.17；`made` 153 / `miss` 152 |

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
vd = list(csv.reader(open(p+'valid_data.csv', encoding='utf-8-sig')))[1:]
oc  = collections.Counter(r[8].strip().lower() for r in vd)
int_ids = all(s.lstrip('-').isdigit() for s in [r[0] for r in vd])
```

数字与本文一致即视为规范未腐坏；任何不一致应先在 main 上重验再修订本文。
