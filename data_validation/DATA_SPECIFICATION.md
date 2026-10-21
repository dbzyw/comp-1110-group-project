# Data Specification for the Basketball Shot Validation Pipeline

## 1. Purpose

This document defines the input contract implemented by the project's
`validation.py`, describes the data files currently kept in this folder, and
records the limits of using those files for model validation.

Validation compares recorded outcomes against the frozen 3D physics
simulation. Data is for evaluation only; it must not be used to tune model
constants. The simulation uses SI units and a right-handed coordinate system:

- `x`: horizontal, from shooter towards basket
- `y`: vertical, positive upwards
- `z`: lateral
- Pure backspin: angular velocity vector `(0, 0, +backspin)` in rad/s

## 2. Files in this folder

| File | Contents | Relevance to `validation.py` |
|---|---|---|
| `extracted_ball_tracks.csv` | 24,073 tracking rows with event, time, shot-clock, and ball-position fields | Frame-level positions only; it does not directly contain shot-level release inputs or outcomes. |
| `selected_shot_initial_conditions.csv` | Five rows with `x_m`, `y_m`, `z_m`, `v0x`, `v0y`, and `v0z` | Has possible position and velocity components, but lacks shot IDs, backspin, outcome labels, and confirmed coordinate/unit metadata. |
| `extract.py` | Extracts ball positions from a local `sample.json` | Writes tracking rows; the expected JSON source is not currently in this folder. |

All data tables use comma-delimited UTF-8 CSV. The original workbook was
converted to `selected_shot_initial_conditions.csv`; it is no longer kept in
this folder. Source provenance and the relationship between the tracking data
and selected initial conditions remain unconfirmed.

## 3. Exact input contract from `validation.py`

### 3.1 Required CSV header

`validation.py` uses `csv.DictReader` and requires every field below to be
present. Keep this spelling and order in validation files:

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
export has a repeated rounded timestamp representation, so recover precise
source times before estimating velocities or frame intervals. Shot-clock
values may be missing.

## 5. Selected initial-conditions CSV

`selected_shot_initial_conditions.csv` has this header:

```csv
x_m,y_m,z_m,v0x,v0y,v0z
```

It contains five records converted from the former workbook, with blank
worksheet rows omitted. The field names suggest positions in metres and
velocity components, but the velocity units, coordinate axes, source method,
and association with individual shots are not documented. It has no shot ID,
backspin, or observed outcome.

The `x_m`, `y_m`, and `z_m` names also do not by themselves prove that these
values use the simulation axes. For example, if `y_m` is meant to be vertical
release height, its observed values (approximately 7.7–10.8 m) need
investigation before they can be used as basketball release heights.

## 6. Preparation requirements before validation

To produce a CSV usable by the current `validation.py`:

1. Establish data provenance, access terms, source units, and source coordinate
   axes.
2. Define one row per shot and assign a unique integer `shot_id`. Keep a
   documented mapping from that ID to source event/frame records.
3. Provide ball-centre release coordinates transformed to the model axes and
   expressed in metres.
4. Provide initial velocity components in the same axes and in metres per
   second. If deriving them from positions, use ordered samples with verified
   timestamps and document the estimation method and uncertainty.
5. Provide backspin in rad/s with its sign converted to the model's positive-z
   convention. Do not use a gyroscope component without verifying sensor
   orientation, units, calibration, and that it represents ball spin.
6. Annotate the observed outcome using one of the supported labels. Preserve
   binary-only labels as binary; do not infer contact subtype.
7. Check all required fields, unique IDs, finite numeric values, outcome
   labels, plausible coordinate ranges, and missing/duplicate records.
8. Keep raw data unchanged and store prepared shot-level data separately.
   Report sample size, exclusions, label granularity, input derivation, and
   uncertainty.

The project's planned sources include public anonymised tracking data and
approximately 20–30 group-member free throws filmed at 60 fps. These are
plans, not confirmation of the current files' provenance or completed
empirical validation. For team-member footage, obtain consent, store it
locally, avoid retaining identifying face data, and delete it after the final
report.

## 7. Readiness of current data

Neither current CSV satisfies the validation input contract:

- The tracking extract has no release velocity, backspin, shot-level outcome,
  or confirmed mapping from event IDs to shots.
- The selected initial-conditions file lacks an integer shot ID, backspin,
  actual outcome, and verified units/axes. Its possible vertical coordinates
  require review.

Do not pass either file directly to `validation.py`. A valid validation file
must contain all nine required columns with integer IDs, finite physical
inputs in the defined units/conventions, and a supported observed outcome.
