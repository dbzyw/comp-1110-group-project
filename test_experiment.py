"""Tests for reproducible sweep CSV outputs."""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import experiment


class SweepCsvTests(unittest.TestCase):
    def test_3d_sweep_csv_records_run_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "sweep.csv"
            shot_count = 2 * 2 * experiment.JITTER_SHOTS
            empty = np.zeros(shot_count, dtype=bool)

            with patch("experiment.batch_simulate",
                       return_value=(empty, empty, empty, empty)):
                experiment.run_sweep(
                    str(output),
                    seed=13,
                    release_pos=np.array([-4.5, 2.1, 0.25]),
                    speed=8.3,
                    angles_deg=np.array([40.0, 50.0]),
                    backspins=np.array([10.0, 20.0]),
                )

            with output.open(newline="", encoding="utf-8") as csv_file:
                rows = list(csv.DictReader(csv_file))

            from plotting import load_sweep
            angles, backspins, probabilities = load_sweep(str(output))

        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["seed"], "13")
        self.assertEqual(rows[0]["seed_strategy_code"], "0")
        self.assertEqual(rows[0]["shots_per_cell"], str(experiment.JITTER_SHOTS))
        self.assertEqual(rows[0]["nominal_speed_m_s"], "8.3000")
        self.assertEqual(rows[0]["release_y_m"], "2.1000")
        self.assertEqual(rows[0]["angle_grid_count"], "2")
        self.assertEqual(rows[0]["backspin_grid_count"], "2")
        np.testing.assert_array_equal(angles, [40.0, 50.0])
        np.testing.assert_array_equal(backspins, [10.0, 20.0])
        np.testing.assert_array_equal(probabilities, np.zeros((2, 2)))
        self.assertAlmostEqual(
            float(rows[0]["rim_distance_m"]),
            np.hypot(-4.5 - experiment.RIM_CENTER[0], 0.25 - experiment.RIM_CENTER[2]),
            places=4,
        )

    def test_2d_sweep_csv_records_speed_and_distance_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "sweep_2d.csv"
            empty = np.zeros(2, dtype=bool)
            result = {
                "made": empty,
                "swish": empty,
                "bank_in": empty,
                "rattle_in": empty,
            }

            with patch("experiment.batch_simulate_2d", return_value=result):
                experiment.run_sweep_2d(
                    str(output),
                    h0=2.1,
                    dist=6.75,
                    angles_deg=np.array([45.0]),
                    backspins=np.array([20.0]),
                    speeds=np.array([7.0, 8.0]),
                )

            with output.open(newline="", encoding="utf-8") as csv_file:
                row = next(csv.DictReader(csv_file))

        self.assertEqual(row["release_height_m"], "2.1000")
        self.assertEqual(row["rim_distance_m"], "6.7500")
        self.assertEqual(row["air_enabled"], "true")
        self.assertEqual(row["speed_sample_count"], "2")
        self.assertEqual(row["speed_grid_min_m_s"], "7.0000")
        self.assertEqual(row["speed_grid_max_m_s"], "8.0000")


if __name__ == "__main__":
    unittest.main()
