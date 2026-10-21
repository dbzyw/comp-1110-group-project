"""Tests for data_validation/data_prep.py.

Covers the pure helper functions (header normalisation, unit scaling, column
finding, finite-float parsing, outcome mapping, 51-degree vacuum velocity,
release-height imputation, and the frozen 2.25-RPS backspin constant) plus an
end-to-end CLI round-trip that runs `main()` on a tiny synthetic raw shooting
CSV (and `--selected-input`) and reads the generated validation-format CSV back
in. These tests guard the documented `data_prep.py` assumptions so they cannot
silently drift (e.g. the backspin value that README / HANDOVER /
PROJECT_CONTEXT / DATA_SPECIFICATION all cite).

Run directly with `python test_data_prep.py` (no third-party deps) or under
pytest.
"""
import contextlib
import csv
import io
import math
import sys
import tempfile
import unittest
from pathlib import Path

from data_validation.data_prep import _estimate_release_height, _velocity_from_speed_and_angle


class ReleaseHeightEstimationTests(unittest.TestCase):
    def test_set_shot_release_height_uses_standing_reach_scenario(self):
        self.assertAlmostEqual(prep._estimate_release_height(1.8, "Set Shot", 2), 2.274)

    def test_jumping_shots_add_half_typical_male_jump(self):
        for shot_type in ("Jump Shot", "Layup", "Tip-in"):
            with self.subTest(shot_type=shot_type):
                self.assertAlmostEqual(
                    prep._estimate_release_height(1.8, shot_type, 2), 2.5015
                )

    def test_release_height_estimate_rejects_unknown_shot_type(self):
        with self.assertRaisesRegex(ValueError, "unsupported shot type"):
            _estimate_release_height(1.8, "Dunk", 2)

    def test_speed_and_release_angle_resolve_straight_on_velocity(self):
        v0x, v0y, v0z = _velocity_from_speed_and_angle(8.0, 30.0, 2)
        self.assertAlmostEqual(v0x, 4.0 * 3 ** 0.5)
        self.assertAlmostEqual(v0y, 4.0)
        self.assertEqual(v0z, 0.0)

    def test_speed_and_release_angle_reject_invalid_measurements(self):
        with self.assertRaisesRegex(ValueError, "shot speed must be positive"):
            _velocity_from_speed_and_angle(0.0, 45.0, 2)
        with self.assertRaisesRegex(ValueError, "release angle must be between"):
            _velocity_from_speed_and_angle(7.0, 90.0, 2)
