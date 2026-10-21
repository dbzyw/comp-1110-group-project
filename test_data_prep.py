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

import data_validation.data_prep as prep


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
            prep._estimate_release_height(1.8, "Dunk", 2)

    def test_release_height_estimate_rejects_nonpositive_or_missing_height(self):
        with self.assertRaisesRegex(ValueError, "player height must be positive"):
            prep._estimate_release_height(0.0, "Set Shot", 3)
        with self.assertRaisesRegex(ValueError, "shot type is missing"):
            prep._estimate_release_height(1.8, "   ", 4)


class UnitScaleTests(unittest.TestCase):
    def test_unit_suffixes_scale_to_metres(self):
        cases = {
            "Distance_from_Basket_m": 1.0,
            "distance_cm": 0.01,
            "Release_Highit_(centimetre)": 0.01,
            "dist_mm": 0.001,
            "height_feet": 0.3048,
            "x_ft": 0.3048,
            "release_inch": 0.0254,
            "v0x": 1.0,  # unitless -> metres by convention
        }
        for header, scale in cases.items():
            with self.subTest(header=header):
                self.assertAlmostEqual(prep._unit_scale(header), scale)

    def test_normalise_header_strips_punctuation_and_case(self):
        self.assertEqual(prep._normalise_header(" Distance_From_Basket(m) "),
                         "distancefrombasketm")


class FindColumnTests(unittest.TestCase):
    def test_finds_by_normalised_alias_and_returns_original_name(self):
        fieldnames = ["Distance_from_Basket_m", "Shot_Result", "Player_ID"]
        self.assertEqual(
            prep._find_column(fieldnames, {"distancefrombasketm", "distance"},
                              "distance from basket"),
            "Distance_from_Basket_m",
        )
        self.assertEqual(
            prep._find_column(fieldnames, {"shotresult"}, "shot outcome"),
            "Shot_Result",
        )

    def test_raises_when_column_absent(self):
        with self.assertRaisesRegex(ValueError, "Could not find"):
            prep._find_column(["foo", "bar"], {"distance"}, "distance")


class ParseFiniteFloatTests(unittest.TestCase):
    def test_parses_finite_numbers(self):
        self.assertEqual(prep._parse_finite_float("3.5", "d", 2), 3.5)
        self.assertEqual(prep._parse_finite_float("-2", "d", 2), -2.0)

    def test_rejects_blank_nonnumeric_nan_inf(self):
        for bad, why in [
            ("", "numeric"),
            ("abc", "numeric"),
            (None, "numeric"),
            ("nan", "finite"),
            ("inf", "finite"),
        ]:
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, why):
                    prep._parse_finite_float(bad, "d", 5)


class MapOutcomeTests(unittest.TestCase):
    def test_maps_various_made_and_miss_tokens_case_insensitively(self):
        for made in ("1", "1.0", "TRUE", "Yes", "made", "make", "hit", "IN", "swish"):
            self.assertEqual(prep._map_outcome(made, 2), "made", msg=made)
        for miss in ("0", "0.0", "false", "no", "MISS", "missed", "out"):
            self.assertEqual(prep._map_outcome(miss, 2), "miss", msg=miss)

    def test_rejects_unknown_outcome(self):
        with self.assertRaisesRegex(ValueError, "unrecognized outcome"):
            prep._map_outcome("maybe", 3)


class InitialVelocityTests(unittest.TestCase):
    def test_51degree_vacuum_solve_matches_recomputed_formula(self):
        # Recompute the documented 51-degree vacuum projectile result so the
        # test is self-consistent with the module's own constants.
        d, ry = 4.0, 2.0
        angle = math.radians(prep.RELEASE_ANGLE_DEG)
        gain = d * math.tan(angle) - (prep.RIM_HEIGHT_M - ry)
        denom = 2.0 * math.cos(angle) ** 2 * gain
        speed = math.sqrt(prep.GRAVITY_M_S2 * d ** 2 / denom)
        vx, vy, vz = prep._initial_velocity(d, ry)
        self.assertAlmostEqual(vx, speed * math.cos(angle), 6)
        self.assertAlmostEqual(vy, speed * math.sin(angle), 6)
        self.assertEqual(vz, 0.0)
        self.assertGreater(vy, 0.0)

    def test_returns_component_defaults_when_no_finite_solution(self):
        for bad_d, bad_ry in [(-1.0, 2.0), (0.0, 2.0), (1.0, 0.0)]:
            with self.subTest(d=bad_d, ry=bad_ry):
                self.assertEqual(prep._initial_velocity(bad_d, bad_ry),
                                 prep.DEFAULT_VELOCITY)


class BackspinConstantTests(unittest.TestCase):
    def test_backspin_is_frozen_midpoint_of_2_0_2_5_rps_target(self):
        # Guard the assumption that README / HANDOVER / PROJECT_CONTEXT /
        # DATA_SPECIFICATION all cite as 14.137167 rad/s (not 23 rad/s).
        self.assertEqual(prep.DEFAULT_BACKSPIN_RPS, 2.25)
        self.assertEqual((prep.BACKSPIN_TARGET_MIN_RPS + prep.BACKSPIN_TARGET_MAX_RPS) / 2.0,
                         2.25)
        self.assertAlmostEqual(prep.DEFAULT_BACKSPIN_RAD_S, 2 * math.pi * 2.25, 6)
        self.assertAlmostEqual(prep.DEFAULT_BACKSPIN_RAD_S, 14.137167, 4)


class MainCliRoundTripTests(unittest.TestCase):
    """Run data_prep.main() end-to-end on synthetic inputs written to a temp dir."""

    def _run(self, argv):
        old = sys.argv
        sys.argv = ["data_prep.py"] + argv
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                prep.main()
        finally:
            sys.argv = old

    def test_cli_converts_raw_dataset_to_validation_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.csv"
            raw.write_text(
                "Distance_from_Basket_m,Shot_Result,Release_Height_m\n"
                "4.0,1,2.0\n"
                "6.0,0,2.3\n",
                encoding="utf-8",
            )
            out = Path(tmp) / "prepared.csv"
            self._run([str(raw), "--output", str(out)])
            with out.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([r["shot_id"] for r in rows], ["1", "2"])
            # distance mapped onto model axis: release_x = -0.375 - distance_m
            self.assertAlmostEqual(float(rows[0]["release_x"]),
                                   prep.RIM_CENTER_X_M - 4.0, 6)
            self.assertAlmostEqual(float(rows[1]["release_x"]),
                                   prep.RIM_CENTER_X_M - 6.0, 6)
            # explicit release height used directly (metres header, scale 1.0)
            self.assertAlmostEqual(float(rows[0]["release_y"]), 2.0, 6)
            self.assertAlmostEqual(float(rows[1]["release_y"]), 2.3, 6)
            self.assertEqual(rows[0]["release_z"], "0.000000")
            # frozen backspin assumption on every row
            for r in rows:
                self.assertEqual(r["backspin"], f"{prep.DEFAULT_BACKSPIN_RAD_S:.6f}")
            # binary outcome mapped
            self.assertEqual(rows[0]["actual_outcome"], "made")
            self.assertEqual(rows[1]["actual_outcome"], "miss")

    def test_cli_appends_selected_initial_conditions(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.csv"
            raw.write_text(
                "Distance_from_Basket_m,Shot_Result,Release_Height_m\n"
                "4.0,1,2.0\n",
                encoding="utf-8",
            )
            sel = Path(tmp) / "sel.csv"
            sel.write_text(
                "x_m,y_m,z_m,v0x,v0y,v0z\n"
                "14.207,7.718,2.534,0.5,0.2,0.5\n",
                encoding="utf-8",
            )
            out = Path(tmp) / "prepared.csv"
            self._run([str(raw), "--output", str(out),
                       "--selected-input", str(sel)])
            with out.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([r["shot_id"] for r in rows], ["1", "2"])
            appended = rows[1]
            # selected row copied straight through, outcome assumed made
            self.assertEqual(appended["release_x"], "14.207000")
            self.assertEqual(appended["release_y"], "7.718000")
            self.assertEqual(appended["actual_outcome"], "made")
            self.assertEqual(appended["backspin"], f"{prep.DEFAULT_BACKSPIN_RAD_S:.6f}")

    def test_cli_refuses_to_overwrite_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.csv"
            raw.write_text(
                "Distance_from_Basket_m,Shot_Result\n"
                "4.0,1\n",
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                # input == output -> argparse parser.error exits
                self._run([str(raw), "--output", str(raw)])


if __name__ == "__main__":
    unittest.main()
