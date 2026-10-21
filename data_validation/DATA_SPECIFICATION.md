# Data Specification for Basketball Shot Validation

## 1. Purpose and scope

This document describes the files currently in `data_validation`, the extraction
script's input/output contract, and the data required by the project's 3D
validation pipeline. It distinguishes observed file contents from assumptions
that still need confirmation. The tracking extract and the spreadsheet are not
yet a complete, validated input to `validation.py`.

The project uses observed shots only to evaluate the frozen physics model, not
to train or tune it. The primary model uses SI units and a right-handed
coordinate system: `x` points from the shooter to the basket, `y` is vertical
up, and `z` is lateral. Confirm and, if necessary, transform source coordinate
axes before using tracking data with that model.

## 2. Files currently present

| File | Observed contents | Current role and limitations |
|---|---|---|
| `extract.py` | Python script reading `sample.json` | Extracts ball positions from the first 50 events and writes `extracted_ball_tracks.csv`. The expected JSON file is not present in this folder. |
| `extracted_ball_tracks.csv` | 24,073 rows; 6 columns; comma-delimited UTF-8 | Ball tracking samples with event, time, shot-clock, and position fields. It does not contain shot labels, release velocities, or spin. |
| `selected_shot_initial_conditions.csv` | 5 rows; 6 columns; comma-delimited UTF-8 | English-named CSV conversion of the selected position and initial-velocity values from the workbook. It has no shot identifier, outcome, backspin, or documented units for the velocity columns. |
| `basketball_shooting_dataset.csv` | 300 rows; 20 columns; comma-delimited UTF-8 | Original source dataset copied into this folder. It includes shot result and aggregate/release measurements, but its provenance and some measurement conventions need confirmation before model validation. |
| `basketball_shots_validation_template.csv` | 300 rows; 9 columns; comma-delimited UTF-8 | Prepared from `C:\Users\yinch\Downloads\basketball_shooting_dataset.csv`. Binary outcomes are mapped to `made`/`miss`; release coordinates, velocity components, and backspin remain blank because they cannot be reliably derived from the source metadata currently available. |

All data tables in this folder use UTF-8 encoding and comma-delimited CSV.
`extract.py` remains a Python script and `DATA_SPECIFICATION.md` remains
documentation; they are not data tables. The original Excel workbook was
replaced by its CSV conversion at the user's request.

The source dataset, collection date, license/terms, event-selection method, and
the relationship between the tracking extract, selected initial conditions,
and the added shooting dataset have not been documented in the files currently
present. The added shooting dataset is not established as NBA SportVU data;
confirm provenance before making that attribution.

## 3. Extraction script contract

`extract.py` currently:

1. Opens a local file named `sample.json` and reads `data["events"]`.
2. Iterates over `data["events"][:50]`.
3. For each event, reads `event["eventId"]` and each `moment`.
4. Reads the moment timestamp from index `1` and shot clock from index `3`.
5. Selects entities whose index `0` equals `-1` (commented as the basketball).
6. Reads position from entity indexes `2`, `3`, and `4`; multiplies each by
   `0.3048` to convert feet to metres and rounds to three decimal places.
7. Writes `event_id`, `timestamp_ms`, `shot_clock`, `x_m`, `y_m`, and `z_m`
   to `extracted_ball_tracks.csv`.

The script relies on positional JSON indexes and a hard-coded input filename.
Before rerunning it on another source, verify that the source uses the same
event/moment/entity layout, that entity ID `-1` denotes the ball, and that
position values are in feet. The script converts units but does not document,
validate, or transform the source coordinate-axis convention.

## 4. Tracking CSV specification

### 4.1 File format and observed profile

- Encoding: readable as UTF-8 (optional BOM accepted).
- Delimiter: comma (`,`).
- Encoding: UTF-8.
- Header: `event_id,timestamp_ms,shot_clock,x_m,y_m,z_m`
- Observed data rows: 24,073.
- Observed event IDs: 49 distinct values, ranging from 1 to 54.
- Observed complete duplicate rows: 10.
- `shot_clock`: 953 blank values; nonblank values range from 0.03 to 24.0.
- `timestamp_ms`: every exported value currently has the same text
  representation, `1.45196E+12`. This representation does not preserve useful
  millisecond-level variation; do not use it to determine frame order, sampling
  interval, or shot duration without recovering the original-precision source.
- Position columns have no blank cells in the current file. Their observed
  numeric ranges are:

| Column | Meaning indicated by name/script | Observed range |
|---|---|---:|
| `x_m` | First source position component, converted to metres | -0.545 to 30.368 |
| `y_m` | Second source position component, converted to metres | -0.258 to 15.592 |
| `z_m` | Third source position component, converted to metres | 0.021 to 5.217 |

These ranges are descriptive checks only. They do not establish the source
coordinate convention, court origin, axis orientation, or whether the named
components correspond to the 3D model's axes.

### 4.2 Data dictionary

| Field | Type | Unit / interpretation | Validation notes |
|---|---|---|---|
| `event_id` | Integer-like identifier | Source event identifier | Not necessarily a shot ID. Confirm event-to-shot meaning and uniqueness before grouping. |
| `timestamp_ms` | Numeric-like timestamp | Intended milliseconds, as indicated by the script's field name | Current exported values are all identically rounded in scientific notation. Recover higher precision and document the epoch/time basis before temporal analysis. |
| `shot_clock` | Numeric, nullable | Source shot-clock units are not specified in the file | 953 blanks are present. Preserve nulls; document whether clock counts up or down and how it relates to timestamps. |
| `x_m` | Numeric | Metres after multiplying source coordinate 1 by `0.3048` | Axis meaning and origin require source metadata. |
| `y_m` | Numeric | Metres after multiplying source coordinate 2 by `0.3048` | Do not assume this is vertical without confirming source axes. |
| `z_m` | Numeric | Metres after multiplying source coordinate 3 by `0.3048` | Do not assume this is lateral without confirming source axes. |

This is a ball-track sample table, not a shot-level validation table. In
particular, it does not identify release samples, provide initial velocity or
backspin, or give the actual outcome label.

## 5. Selected initial-conditions CSV specification

`selected_shot_initial_conditions.csv` was converted from the workbook that
previously contained one sheet named `Sheet1`. It is UTF-8, comma-delimited,
and has the header:

```text
x_m, y_m, z_m, v0x, v0y, v0z
```

It contains five data rows. The source worksheet's intervening blank rows were
omitted; worksheet row numbers were not carried over as shot identifiers. The
position field names indicate metres. The velocity field names appear to be
initial velocity components, but their units, axis convention, derivation
method, and association with individual shots are not recorded. The source
workbook contained no shot ID, actual outcome, backspin rate, timestamp, or
provenance metadata. These rows therefore cannot currently be matched reliably
to tracking events or passed directly to the validation pipeline.

When importing, retain the header and do not treat record order as a shot
identifier.

## 6. Required shot-level validation input

The project's `validation.py` expects a shot-level CSV with this exact header
and comma delimiter:

```csv
shot_id,release_x,release_y,release_z,v0x,v0y,v0z,backspin,actual_outcome
```

| Field | Required meaning | Unit / allowed values |
|---|---|---|
| `shot_id` | Stable unique identifier for one shot | Non-empty string or integer-like ID; must link to source records. |
| `release_x`, `release_y`, `release_z` | Ball-centre position at release in the 3D model coordinate system | Metres; `y` is vertical and `z` is lateral. |
| `v0x`, `v0y`, `v0z` | Initial ball-centre velocity components at release | Metres per second, using the same axes as the release position. |
| `backspin` | Release backspin rate used by the model | Radians per second; the model convention is `omega = (0, 0, +backspin)`. |
| `actual_outcome` | Observed result for that same shot | Detailed: `swish`, `rim-in`, `board-in`, or `miss`. Legacy made/miss labels such as `made`, `in`, `bounce-in`, `out`, or `no` support binary analysis only. |

Use one record per shot, not one record per tracking frame. Keep a separate
traceable link from each `shot_id` to its source event/frame range and
annotation. If the outcome is only known as made/missed, do not fabricate one
of the three made-shot subtypes; four-class metrics are not supported by such
labels.

### 6.1 Prepared template from the shooting dataset

`basketball_shots_validation_template.csv` follows the exact nine-column
validation header above and has one row for each of the 300 source records.
Its `shot_id` values (`source_row_0001` through `source_row_0300`) identify
source data-row positions, not verified shot identifiers. They preserve a
traceable row-level link to `basketball_shooting_dataset.csv`, the unchanged
source copy now stored alongside the template.

The source's `Shot_Result` values were `0` or `1`; they were mapped to `miss`
and `made`, respectively. The prepared file contains 148 `made` and 152
`miss` labels. These are binary labels only and do not support the four-class
outcome analysis.

The source also has `Shot_Speed_m_s`, `Release_Angle_deg`, and gyroscope
columns, but their exact measurement definitions, coordinate axes, and
relationship to the simulation's release vector and backspin convention are
not established. Therefore the template leaves `release_x`, `release_y`,
`release_z`, `v0x`, `v0y`, `v0z`, and `backspin` blank rather than assuming a
release origin, planar motion, angle convention, or gyro axis. The file is a
staging template for later review; it is not ready to pass to `validation.py`
until these inputs are measured or derived with documented, validated
conventions. Keep the original dataset unchanged.

## 7. Data preparation and acceptance checks

Before running validation:

1. **Record provenance:** source name, source URL or local source identifier,
   access date, license/terms, extraction date, and any filtering or selection
   criteria.
2. **Preserve originals:** keep the source JSON/workbook unchanged; write
   normalized and derived data to separate files.
3. **Confirm source semantics:** verify entity IDs, source units, coordinate
   axes/origin/directions, timestamp epoch and precision, shot-clock meaning,
   and event/shot relationships from source documentation.
4. **Recover temporal precision:** obtain the original timestamp values rather
   than relying on the rounded values in the current CSV. Sort samples within
   each shot by precise time before estimating motion.
5. **Identify shots and release:** define a reproducible event-to-shot and
   release-frame rule. Derive velocity from ordered positions only after
   confirming coordinate mapping and time units; document the estimation
   method and uncertainty.
6. **Supply missing model inputs:** estimate or obtain backspin and actual
   outcome for each shot. Record the source or annotation method. The current
   files do not provide either field.
7. **Normalize to model coordinates and SI:** convert to metres and metres per
   second, map axes into `x` forward, `y` up, `z` lateral, and apply the
   project's court geometry consistently.
8. **Check records:** require all numeric model inputs to be finite; check
   unique shot IDs, non-empty outcomes, plausible release positions/speeds,
   valid units, and correct label spelling/case. Investigate duplicates and
   missing values rather than silently dropping or filling them.
9. **Keep labels independent:** do not use observed outcome labels to tune
   frozen model constants or choose release parameters.
10. **Report limitations:** include sample size, missing/excluded records,
    label granularity, input derivation, and uncertainty. Report binary
    agreement with a Wilson 95% confidence interval and Cohen's kappa where
    supported; report a four-class confusion matrix only when detailed labels
    are available.

The planned validation sources elsewhere in the project documentation are
public anonymised NBA tracking data and approximately 20–30 group-member free
throws filmed at 60 fps. Those are plans, not proof of the current files'
provenance or a completed empirical validation. For self-filmed data, obtain
participants' consent, keep footage local, avoid retaining identifying face
data, and delete footage after the final report as specified by the project
ethics notes.

## 8. Current readiness summary

The extracted CSV can support inspection of sampled ball positions after its
source axes and time precision are resolved. The spreadsheet appears to hold
five selected position/velocity records, but currently lacks documented units
for velocity and links to events or outcomes. Neither file alone satisfies the
shot-level validation schema. The new template carries the imported dataset's
binary labels but intentionally leaves its seven required physical inputs
empty. Validation should wait until provenance, coordinate mapping, precise
timing where applicable, shot identity, release parameters, backspin, and
outcome labels are available and checked.
