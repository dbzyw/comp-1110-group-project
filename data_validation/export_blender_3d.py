"""Export validation trajectories in a Blender-friendly CSV and JSON format.

The exporter reads the authoritative validation CSV, runs the same
``simulation.simulate_shot`` prediction used by ``validation.py``, and writes:

* ``trajectories/shot_<id>.csv`` with ``frame,x,y,z,vx,vy,vz`` at 60 fps;
* ``shots.json`` with source inputs, prediction metadata, and relative paths.

The manifest is intentionally general: it supports made and missed shots and
does not use the three-shot-only schema consumed by blender_3d/build_blender.py.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collision import RIM_HEIGHT
from simulation import simulate_shot
from validation import _to_binary, load_shots


FPS = 60.0
DEFAULT_INPUT = ROOT / "data_validation" / "valid_data_3D.csv"
DEFAULT_OUTPUT = ROOT / "data_validation" / "blender_3d_validation"
TRAJECTORY_COLUMNS = "frame,x,y,z,vx,vy,vz"


def _score_frame(result: dict) -> float | None:
    """Return the interpolated frame for a made shot's downward hoop crossing."""
    if result["outcome"] == "miss":
        return None

    times = result["times"]
    states = result["states"]
    crossings = np.where(
        (states[1:, 1] <= RIM_HEIGHT) & (states[:-1, 1] > RIM_HEIGHT)
    )[0]
    if len(crossings) == 0:
        raise RuntimeError(
            "A made shot has no downward crossing of the hoop-height plane."
        )

    index = int(crossings[0])
    y_before, y_after = states[index, 1], states[index + 1, 1]
    fraction = (y_before - RIM_HEIGHT) / (y_before - y_after)
    crossing_time = times[index] + fraction * (times[index + 1] - times[index])
    return float(crossing_time * FPS + 1.0)


def _sample_at_fps(times: np.ndarray, states: np.ndarray) -> np.ndarray:
    """Linearly sample a simulated trajectory at the Blender frame rate."""
    end_time = float(times[-1])
    sample_times = np.arange(0.0, end_time, 1.0 / FPS)
    if len(sample_times) == 0 or not math.isclose(
        float(sample_times[-1]), end_time, abs_tol=1e-12
    ):
        sample_times = np.append(sample_times, end_time)

    sampled_states = np.column_stack(
        [np.interp(sample_times, times, states[:, column]) for column in range(6)]
    )
    frames = np.arange(1, len(sample_times) + 1, dtype=float)
    return np.column_stack((frames, sampled_states))


def export_validation_trajectories(
    input_csv: Path, output_dir: Path, *, overwrite: bool = False
) -> Path:
    """Create a 60-fps trajectory export and return its manifest path."""
    input_csv = Path(input_csv).resolve()
    output_dir = Path(output_dir).resolve()
    if not input_csv.is_file():
        raise FileNotFoundError(f"Validation CSV does not exist: {input_csv}")
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output directory already exists: {output_dir}. "
                "Pass --overwrite to replace this export."
            )
        shutil.rmtree(output_dir)

    shots = load_shots(input_csv)
    trajectories_dir = output_dir / "trajectories"
    trajectories_dir.mkdir(parents=True)
    manifest_shots = []

    for shot in shots:
        result = simulate_shot(
            shot["release_pos"], shot["release_vel"], shot["backspin"]
        )
        trajectory = _sample_at_fps(result["times"], result["states"])
        shot_id = shot["shot_id"]
        trajectory_path = trajectories_dir / f"shot_{shot_id}.csv"
        np.savetxt(
            trajectory_path,
            trajectory,
            delimiter=",",
            comments="",
            fmt="%.6f",
            header=TRAJECTORY_COLUMNS,
        )

        predicted_outcome = result["outcome"]
        actual_outcome = shot["actual_outcome"]
        actual_binary = _to_binary(actual_outcome)
        predicted_binary = _to_binary(predicted_outcome)
        manifest_shots.append(
            {
                "shot_id": shot_id,
                "trajectory_csv": str(
                    trajectory_path.relative_to(output_dir)
                ).replace("\\", "/"),
                "release_position_m": [float(value) for value in shot["release_pos"]],
                "release_velocity_m_s": [
                    float(value) for value in shot["release_vel"]
                ],
                "backspin_rad_s": float(shot["backspin"]),
                "actual_outcome": actual_outcome,
                "actual_binary": actual_binary,
                "predicted_outcome": predicted_outcome,
                "predicted_binary": predicted_binary,
                "match": predicted_binary == actual_binary,
                "contacts": [str(contact) for contact in result["contacts"]],
                "reason": result["reason"],
                "score_frame": _score_frame(result),
                "points": int(len(trajectory)),
                "t_end_s": float(result["times"][-1]),
            }
        )

    manifest = {
        "schema_version": 1,
        "source_csv": input_csv.name,
        "coordinate_system": {
            "units": "SI",
            "x": "from shooter towards basket",
            "y": "vertical, positive upwards",
            "z": "lateral",
        },
        "frames_per_second": FPS,
        "trajectory_columns": TRAJECTORY_COLUMNS.split(","),
        "shots": manifest_shots,
    }
    manifest_path = output_dir / "shots.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export validation trajectories for a general Blender renderer."
    )
    parser.add_argument(
        "--input", type=Path, default=DEFAULT_INPUT, help="Validation CSV to simulate."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory for shots.json and trajectory CSV files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory.",
    )
    args = parser.parse_args(argv)
    manifest_path = export_validation_trajectories(
        args.input, args.output, overwrite=args.overwrite
    )
    print(f"Exported {len(load_shots(args.input))} shots to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
