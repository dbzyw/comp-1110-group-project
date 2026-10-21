import unittest

from data_validation.data_prep import _estimate_release_height


class ReleaseHeightEstimationTests(unittest.TestCase):
    def test_set_shot_release_height_uses_standing_reach_scenario(self):
        self.assertAlmostEqual(_estimate_release_height(1.8, "Set Shot", 2), 2.274)

    def test_jumping_shots_add_half_typical_male_jump(self):
        for shot_type in ("Jump Shot", "Layup", "Tip-in"):
            with self.subTest(shot_type=shot_type):
                self.assertAlmostEqual(
                    _estimate_release_height(1.8, shot_type, 2), 2.5015
                )

    def test_release_height_estimate_rejects_unknown_shot_type(self):
        with self.assertRaisesRegex(ValueError, "unsupported shot type"):
            _estimate_release_height(1.8, "Dunk", 2)
