import unittest

from data_validation.data_prep import _estimate_release_height, _velocity_from_speed_and_angle


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
