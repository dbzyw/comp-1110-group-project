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

    def test_board_face_and_corner_at_multiple_ball_sizes(self):
        cases = [
            ([-0.08, 3.4, 0.2], 0.12, True),
            ([-0.13, 3.4, 0.2], 0.12, False),
            ([-0.05, 2.82, 0.0], 0.12, True),
            ([-0.08, 2.80, 0.0], 0.12, False),
            ([-0.05, 2.82, 0.92], 0.12, True),
        ]
        for position, radius, expected_hit in cases:
            with self.subTest(position=position, radius=radius):
                self.assertEqual(
                    collision.detect_backboard(position, radius) is not None,
                    expected_hit,
                )

    def test_batch_radius_matches_scalar(self):
        points = np.array([[-0.10, 3.2, 0.0], [-0.14, 3.2, 0.0]])
        hit, normals, penetration = collision.detect_backboard_batch(points, 0.15)
        for index, point in enumerate(points):
            scalar = collision.detect_backboard(point, 0.15)
            self.assertEqual(bool(hit[index]), scalar is not None)
            if scalar is not None:
                np.testing.assert_allclose(normals[index], scalar.normal)
                self.assertAlmostEqual(penetration[index], scalar.penetration)


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

    def test_rim_contact_changes_with_ball_radius(self):
        center = collision.RIM_CENTER.copy()
        self.assertIsNone(collision.detect_rim(center, ball_radius=0.12))
        larger_ball_contact = collision.detect_rim(center, ball_radius=0.23)
        self.assertIsNotNone(larger_ball_contact)
        self.assertAlmostEqual(larger_ball_contact.penetration, 0.23 - 0.225)

    def test_rim_batch_accepts_custom_ball_radius(self):
        points = np.array([collision.RIM_CENTER, [0.0, 4.0, 0.0]])
        hit, normals, penetration = collision.detect_rim_batch(points, 0.23)
        for index, point in enumerate(points):
            scalar = collision.detect_rim(point, 0.23)
            self.assertEqual(bool(hit[index]), scalar is not None)
            if scalar is not None:
                np.testing.assert_allclose(normals[index], scalar.normal)
                self.assertAlmostEqual(penetration[index], scalar.penetration)


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

    def test_restitution_range_and_oblique_contact(self):
        # Normal is diagonal; change only the normal component, not the tangent.
        normal = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
        tangent = np.array([1.0, -1.0, 0.0]) / np.sqrt(2.0)
        incoming = -4.0 * normal + 3.0 * tangent
        for restitution in (0.0, 0.5, 1.0):
            with self.subTest(restitution=restitution):
                outgoing = collision.reflect(incoming, normal, restitution)
                self.assertAlmostEqual(np.dot(outgoing, normal), 4.0 * restitution)
                self.assertAlmostEqual(np.dot(outgoing, tangent), 3.0)

    def test_tangential_contact_does_not_create_bounce(self):
        velocity = np.array([0.0, 2.0, 3.0])
        normal = np.array([1.0, 0.0, 0.0])
        np.testing.assert_allclose(collision.reflect(velocity, normal), velocity)

    def test_position_correction_can_be_disabled(self):
        position = np.array([-0.05, 3.2, 0.0])
        hit = collision.detect_backboard(position)
        corrected, _ = collision.resolve(position, [5.0, 0.0, 0.0], hit)
        unchanged, _ = collision.resolve(
            position, [5.0, 0.0, 0.0], hit, correct_position=False
        )
        self.assertGreater(np.linalg.norm(corrected - position), 0.0)
        np.testing.assert_allclose(unchanged, position)

    def test_invalid_ball_radius_is_rejected(self):
        with self.assertRaises(ValueError):
            collision.detect_rim(collision.RIM_CENTER, ball_radius=0.0)


if __name__ == "__main__":
    unittest.main()
