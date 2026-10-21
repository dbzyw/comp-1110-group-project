"""Prepare a raw basketball shooting CSV for the project's validation.py.

Assumptions:
* Distance is a straight-on horizontal distance to the rim centre.
* The 51-degree vacuum projectile calculation ignores drag, Magnus lift, and
  rim/board contact. If no finite solution exists, use the requested component
  defaults (6 m/s, 4 m/s, 0 m/s).
* Missing release height defaults to 2.0 m; lateral position and velocity are
  assumed zero; backspin is fixed at 23 rad/s.
"""

import argparse
import csv
import math
import re
import sys
from pathlib import Path


FIELDS = [
    "shot_id",
    "release_x",
    "release_y",
    "release_z",
    "v0x",
    "v0y",
    "v0z",
    "backspin",
    "actual_outcome",
]

RIM_CENTER_X_M = -0.375
RIM_HEIGHT_M = 3.05
GRAVITY_M_S2 = 9.81
RELEASE_ANGLE_DEG = 51.0
DEFAULT_RELEASE_HEIGHT_M = 2.0
DEFAULT_VELOCITY = (6.0, 4.0, 0.0)
DEFAULT_BACKSPIN_RAD_S = 23.0


def _normalise_header(value):
    return re.sub(r"[^a-z0-9]", "", value.strip().lower())


def _find_column(fieldnames, aliases, description):
    lookup = {_normalise_header(name): name for name in fieldnames if name}
    for alias in aliases:
        if alias in lookup:
            return lookup[alias]
    raise ValueError(
        f"Could not find the {description} column. Available columns: {fieldnames}"
    )


def _unit_scale(header):
    name = header.strip().lower()
    if any(unit in name for unit in ("centimeter", "centimetre", "_cm", "(cm)")):
        return 0.01
    if any(unit in name for unit in ("millimeter", "millimetre", "_mm", "(mm)")):
        return 0.001
    if any(unit in name for unit in ("feet", "foot", "_ft", "(ft)")):
        return 0.3048
    if any(unit in name for unit in ("inch", "_in", "(in)")):
        return 0.0254
    return 1.0


def _parse_finite_float(value, field, row_number):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Row {row_number}: {field} must be numeric, got {value!r}"
        ) from exc
    if not math.isfinite(number):
        raise ValueError(f"Row {row_number}: {field} must be finite, got {value!r}")
    return number


def _map_outcome(value, row_number):
    label = str(value).strip().lower()
    if label in {"1", "1.0", "true", "yes", "made", "make", "hit", "in", "swish"}:
        return "made"
    if label in {"0", "0.0", "false", "no", "miss", "missed", "out"}:
        return "miss"
    raise ValueError(
        f"Row {row_number}: unrecognized outcome {value!r}; expected a made/miss value"
    )


def _initial_velocity(distance_m, release_y_m):
    angle = math.radians(RELEASE_ANGLE_DEG)
    cos_angle = math.cos(angle)
    height_gain_at_unit_speed = (
        distance_m * math.tan(angle) - (RIM_HEIGHT_M - release_y_m)
    )
    denominator = 2.0 * cos_angle**2 * height_gain_at_unit_speed
    if distance_m > 0.0 and denominator > 0.0:
        speed_squared = GRAVITY_M_S2 * distance_m**2 / denominator
        if math.isfinite(speed_squared) and speed_squared > 0.0:
            speed = math.sqrt(speed_squared)
            return speed * cos_angle, speed * math.sin(angle), 0.0
    return DEFAULT_VELOCITY


def _read_rows(input_path):
    with input_path.open("r", encoding="utf-8-sig", newline="") as source:
        sample = source.read(8192)
        source.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(source, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError(f"{input_path} has no header row.")

        distance_column = _find_column(
            reader.fieldnames,
            {
                "distancefrombasket",
                "distancefrombasketm",
                "distance",
                "shotdistance",
                "shotdistancem",
                "releasedistance",
                "releasedistancem",
            },
            "distance from basket",
        )
        outcome_column = _find_column(
            reader.fieldnames,
            {"madeshots", "shotresult", "shotaccuracy", "outcome", "result"},
            "shot outcome",
        )
        height_column = next(
            (
                name
                for name in reader.fieldnames
                if _normalise_header(name)
                in {"releaseheight", "releaseheightm", "releaseheightcm",
                    "releaseheightft", "releaseheightin"}
            ),
            None,
        )

        distance_scale = _unit_scale(distance_column)
        height_scale = _unit_scale(height_column) if height_column else 1.0
        output_rows = []
        for row_number, raw in enumerate(reader, start=2):
            if not any(value not in (None, "") for value in raw.values()):
                continue
            if None in raw:
                raise ValueError(f"Row {row_number}: extra values beyond the header.")

            distance_value = raw.get(distance_column, "")
            if distance_value is None or not distance_value.strip():
                raise ValueError(f"Row {row_number}: distance from basket is missing.")
            distance_m = _parse_finite_float(
                distance_value, distance_column, row_number
            ) * distance_scale
            if distance_m < 0.0:
                raise ValueError(
                    f"Row {row_number}: distance from basket cannot be negative."
                )

            release_y_value = raw.get(height_column, "") if height_column else ""
            if release_y_value is None or not release_y_value.strip():
                release_y_m = DEFAULT_RELEASE_HEIGHT_M
            else:
                release_y_m = _parse_finite_float(
                    release_y_value, height_column, row_number
                ) * height_scale
                if release_y_m < 0.0:
                    raise ValueError(
                        f"Row {row_number}: release height cannot be negative."
                    )

            v0x, v0y, v0z = _initial_velocity(distance_m, release_y_m)
            outcome = _map_outcome(raw.get(outcome_column, ""), row_number)

            # In the simulation's court frame, the rim centre is at x=-0.375 m
            # and a straight-on shooter is farther in the negative-x direction.
            output_rows.append(
                {
                    "shot_id": len(output_rows) + 1,
                    "release_x": f"{RIM_CENTER_X_M - distance_m:.6f}",
                    "release_y": f"{release_y_m:.6f}",
                    "release_z": "0.000000",
                    "v0x": f"{v0x:.6f}",
                    "v0y": f"{v0y:.6f}",
                    "v0z": f"{v0z:.6f}",
                    "backspin": f"{DEFAULT_BACKSPIN_RAD_S:.6f}",
                    "actual_outcome": outcome,
                }
            )
    if not output_rows:
        raise ValueError(f"{input_path} contains no shot records.")
    return output_rows


def _read_selected_initial_conditions(input_path, first_shot_id, assumed_outcome):
    """Map precomputed positions/velocities into validation rows."""
    with input_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        expected = ["x_m", "y_m", "z_m", "v0x", "v0y", "v0z"]
        if reader.fieldnames != expected:
            raise ValueError(
                f"{input_path} must have exactly these columns: {expected}"
            )
        rows = []
        for row_number, raw in enumerate(reader, start=2):
            if not any(value not in (None, "") for value in raw.values()):
                continue
            try:
                values = {
                    field: _parse_finite_float(raw[field], field, row_number)
                    for field in expected
                }
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{input_path}: {exc}") from exc
            if values["y_m"] < 0.0:
                raise ValueError(
                    f"{input_path} row {row_number}: y_m cannot be below zero."
                )
            shot_id = first_shot_id + len(rows)
            rows.append(
                {
                    "shot_id": shot_id,
                    "release_x": f"{values['x_m']:.6f}",
                    "release_y": f"{values['y_m']:.6f}",
                    "release_z": f"{values['z_m']:.6f}",
                    "v0x": f"{values['v0x']:.6f}",
                    "v0y": f"{values['v0y']:.6f}",
                    "v0z": f"{values['v0z']:.6f}",
                    "backspin": f"{DEFAULT_BACKSPIN_RAD_S:.6f}",
                    "actual_outcome": assumed_outcome,
                }
            )
    return rows


def _print_preview(rows):
    print("Preview (first five rows):")
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(FIELDS)
    for row in rows[:5]:
        writer.writerow([row[field] for field in FIELDS])


def main():
    parser = argparse.ArgumentParser(
        description="Convert a raw basketball shooting CSV to validation.py format."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="basketball_shooting_dataset.csv",
        help="raw source CSV (default: basketball_shooting_dataset.csv)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="output CSV (default: valid_data.csv beside this script)",
    )
    parser.add_argument(
        "--selected-input",
        default=None,
        help="optionally append x_m,y_m,z_m,v0x,v0y,v0z rows from this CSV",
    )
    parser.add_argument(
        "--selected-outcome",
        choices=("made", "miss"),
        default="made",
        help="assumed binary label for selected-input rows (default: made)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    input_path = Path(args.input).expanduser()
    if not input_path.is_absolute():
        candidates = [Path.cwd() / input_path, script_dir / input_path]
        input_path = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    if not input_path.is_file():
        parser.error(
            f"input file not found: {input_path}. Place basketball_shooting_dataset.csv "
            "beside this script or provide its path."
        )

    output_path = (
        Path(args.output).expanduser()
        if args.output
        else script_dir / "valid_data.csv"
    )
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    if input_path.resolve() == output_path.resolve():
        parser.error("input and output paths must be different; refusing to overwrite input.")

    try:
        rows = _read_rows(input_path)
        if args.selected_input:
            selected_path = Path(args.selected_input).expanduser()
            if not selected_path.is_absolute():
                selected_candidates = [
                    Path.cwd() / selected_path,
                    script_dir / selected_path,
                ]
                selected_path = next(
                    (
                        candidate
                        for candidate in selected_candidates
                        if candidate.is_file()
                    ),
                    selected_candidates[0],
                )
            if not selected_path.is_file():
                raise FileNotFoundError(
                    f"selected initial-conditions file not found: {selected_path}"
                )
            rows.extend(
                _read_selected_initial_conditions(
                    selected_path, len(rows) + 1, args.selected_outcome
                )
            )
    except (OSError, csv.Error, ValueError) as exc:
        parser.error(str(exc))

    _print_preview(rows)
    with output_path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved {len(rows)} shots to: {output_path}")


if __name__ == "__main__":
    main()
