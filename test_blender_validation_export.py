"""Tests for data_validation/export_blender_3d.py."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from data_validation.export_blender_3d import export_validation_trajectories


class BlenderValidationExportTests(unittest.TestCase):
    def test_exports_blender_compatible_trajectory_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            input_csv = directory / "shots.csv"
            input_csv.write_text(
                "shot_id,release_x,release_y,release_z,v0x,v0y,v0z,backspin,actual_outcome\n"
                "1,-4.57,2.0,0.0,4.72,5.83,0.0,14.137167,made\n",
                encoding="utf-8",
            )
            manifest_path = export_validation_trajectories(
                input_csv, directory / "export"
            )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["frames_per_second"], 60.0)
            self.assertEqual(
                manifest["trajectory_columns"],
                ["frame", "x", "y", "z", "vx", "vy", "vz"],
            )
            self.assertEqual(len(manifest["shots"]), 1)

            shot = manifest["shots"][0]
            self.assertEqual(shot["shot_id"], 1)
            trajectory_path = manifest_path.parent / shot["trajectory_csv"]
            with trajectory_path.open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(
                list(rows[0]),
                ["frame", "x", "y", "z", "vx", "vy", "vz"],
            )
            self.assertEqual(len(rows), shot["points"])
            self.assertEqual(rows[0]["frame"], "1.000000")
            self.assertEqual(rows[0]["x"], "-4.570000")


if __name__ == "__main__":
    unittest.main()
