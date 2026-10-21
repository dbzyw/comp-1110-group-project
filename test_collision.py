"""Focused tests for collision geometry and velocity response."""

import unittest

import numpy as np

import collision


class BackboardTests(unittest.TestCase):
    def test_face_contact_and_normal(self):
        hit = collision.detect_backboard([-0.05, 3.2, 0.0])
        self.assertIsNotNone(hit)
        np.testing.assert_allclose(hit.normal, [-1.0, 0.0, 0.0])
        self.assertAlmostEqual(hit.penetration, 0.07)

    def test_ball_can_touch_board_edge_with_centre_outside_rectangle(self):
        # The centre is 5 cm below the board, but the sphere overlaps its edge.
        hit = collision.detect_backboard([-0.05, 2.85, 0.0])
        self.assertIsNotNone(hit)
        self.assertGreater(hit.penetration, 0.0)
        self.assertLess(hit.normal[1], 0.0)

    def test_batch_matches_scalar_including_edge(self):
        points = np.array([
            [-0.05, 3.2, 0.0],
            [-0.05, 2.85, 0.0],
            [-1.0, 3.2, 0.0],
            [0.0, 3.2, 0.0],
        ])
        hits, normals, penetrations = collision.detect_backboard_batch(points)
        for index, point in enumerate(points):
            scalar = collision.detect_backboard(point)
            self.assertEqual(bool(hits[index]), scalar is not None)
            if scalar is not None:
                np.testing.assert_allclose(normals[index], scalar.normal)
                self.assertAlmostEqual(penetrations[index], scalar.penetration)


class RimTests(unittest.TestCase):
    def test_axis_distance_is_not_mistaken_for_contact(self):
        # On the axis, the nearest distance to a 0.225 m ring is 0.225 m,
        # larger than the 0.12 m ball radius.
        self.assertIsNone(collision.detect_rim(collision.RIM_CENTER))

    def test_ring_contact(self):
        point = [collision.RIM_CENTER[0] + collision.RIM_RADIUS,
                 collision.RIM_HEIGHT, collision.RIM_CENTER[2]]
        hit = collision.detect_rim(point)
        self.assertIsNotNone(hit)
        self.assertAlmostEqual(hit.penetration, collision.BALL_RADIUS)
        np.testing.assert_allclose(hit.normal, [1.0, 0.0, 0.0])

    def test_batch_matches_scalar(self):
        points = np.array([
            collision.RIM_CENTER,
            [collision.RIM_CENTER[0] + collision.RIM_RADIUS,
             collision.RIM_HEIGHT, collision.RIM_CENTER[2]],
            [0.0, 4.0, 0.0],
        ])
        hits, normals, penetrations = collision.detect_rim_batch(points)
        for index, point in enumerate(points):
            scalar = collision.detect_rim(point)
            self.assertEqual(bool(hits[index]), scalar is not None)
            if scalar is not None:
                np.testing.assert_allclose(normals[index], scalar.normal)
                self.assertAlmostEqual(penetrations[index], scalar.penetration)


class ResponseTests(unittest.TestCase):
    def test_restitution_changes_only_normal_component(self):
        velocity = np.array([5.0, -2.0, 1.0])
        normal = np.array([-1.0, 0.0, 0.0])
        result = collision.reflect(velocity, normal, 0.7)
        np.testing.assert_allclose(result, [-3.5, -2.0, 1.0])

    def test_separating_velocity_is_unchanged(self):
        velocity = np.array([-3.0, 1.0, 0.0])
        normal = np.array([-1.0, 0.0, 0.0])
        np.testing.assert_allclose(collision.reflect(velocity, normal), velocity)

    def test_invalid_restitution_is_rejected(self):
        with self.assertRaises(ValueError):
            collision.reflect([1.0, 0.0, 0.0], [1.0, 0.0, 0.0], 1.2)


if __name__ == "__main__":
    unittest.main()
