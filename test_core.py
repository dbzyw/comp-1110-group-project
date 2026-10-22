"""
test_core.py — 核心物理 / 碰撞 / 模拟的单元测试。

无第三方依赖, 直接运行:  python test_core.py
(也可用 pytest:  pytest test_core.py)
"""

import numpy as np

from data_validation.data_prep import DEFAULT_BACKSPIN_RAD_S
from physics import (
    gravity_force, drag_force, magnus_force, release_velocity, spin_vector,
    BALL_MASS, G,
)
from collision import (
    detect_backboard, detect_backboard_batch, detect_rim, reflect,
    RESTITUTION, RIM_CENTER, BALL_RADIUS,
)
from simulation import simulate_shot


# ---------------------------------------------------------------------------
# 物理
# ---------------------------------------------------------------------------
def test_gravity_direction_and_magnitude():
    f = gravity_force()
    assert f.shape == (3,)
    assert f[0] == 0.0 and f[2] == 0.0
    assert np.isclose(f[1], -BALL_MASS * G), "重力应为 (0, -m*g, 0)"


def test_drag_opposes_velocity_and_scales_with_v2():
    v = np.array([7.0, 2.0, -1.0])
    fd = drag_force(v)
    assert float(np.dot(fd, v)) < 0.0, "阻力应与速度反向"
    fd2 = drag_force(2.0 * v)
    assert np.allclose(fd2, 4.0 * fd), "阻力应正比于 |v|^2"


def test_magnus_backspin_gives_upward_lift():
    omega = spin_vector(DEFAULT_BACKSPIN_RAD_S)  # 后旋 (0,0,+ω)
    v = np.array([7.0, 1.0, 0.0])          # 前上方速度
    fm = magnus_force(v, omega)
    assert fm[1] > 0.0, "后旋应产生向上升力"


def test_release_velocity_components():
    assert np.allclose(release_velocity(10.0, 90.0), [0.0, 10.0, 0.0])
    assert np.allclose(release_velocity(10.0, 0.0), [10.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# 碰撞
# ---------------------------------------------------------------------------
def test_reflect_restitution_flips_normal_only():
    v = np.array([5.0, -2.0, 0.0])
    n = np.array([-1.0, 0.0, 0.0])         # 篮板法向
    vr = reflect(v, n, RESTITUTION)
    assert np.isclose(vr[0], -RESTITUTION * 5.0), "法向分量应反转并乘 e"
    assert np.isclose(vr[1], -2.0), "切向分量应不变"


def test_reflect_does_nothing_when_moving_away():
    v = np.array([-3.0, 0.0, 0.0])         # 已朝 -x 远离
    n = np.array([-1.0, 0.0, 0.0])
    assert np.allclose(reflect(v, n), v)


def test_backboard_side_aware_normal():
    # -x 侧 -> 法向 (-1,0,0)
    c1 = detect_backboard(np.array([-0.05, 3.2, 0.0]))
    assert c1 is not None and c1.normal[0] == -1.0
    # +x 侧 -> 法向 (+1,0,0)
    c2 = detect_backboard(np.array([0.05, 3.2, 0.0]))
    assert c2 is not None and c2.normal[0] == 1.0


def test_backboard_batch_matches_scalar():
    pts = np.array([[-0.05, 3.2, 0.0], [0.05, 3.2, 0.0], [-1.0, 3.2, 0.0]])
    hit, norm, pen = detect_backboard_batch(pts)
    for i, p in enumerate(pts):
        c = detect_backboard(p)
        assert (c is not None) == bool(hit[i])
        if c is not None:
            assert np.allclose(norm[i], c.normal)
            assert np.isclose(pen[i], c.penetration)


def test_rim_swish_returns_none():
    # 球心正对筐心 -> 空心, 无碰撞
    c = detect_rim(np.array([RIM_CENTER[0], 3.10, 0.0]))
    assert c is None


def test_rim_clip_detected():
    # 球心在筐洞内但贴近圆环 (水平偏移 0.15 m) -> 擦框碰撞
    c = detect_rim(np.array([RIM_CENTER[0] + 0.15, RIM_CENTER[1], 0.0]))
    assert c is not None


# ---------------------------------------------------------------------------
# 模拟
# ---------------------------------------------------------------------------
def test_simulate_swish():
    v0 = release_velocity(7.5, 51.0)
    res = simulate_shot([-4.57, 2.0, 0.0], v0, DEFAULT_BACKSPIN_RAD_S)
    assert res["outcome"] == "swish", f"预期 swish, 实得 {res['outcome']}"


def test_simulate_dt_guard():
    try:
        simulate_shot([-4.57, 2.0, 0.0], [4.7, 5.8, 0.0], DEFAULT_BACKSPIN_RAD_S, dt=0.1)
        raise AssertionError("dt=0.1 应触发 ValueError")
    except ValueError:
        pass


def test_simulate_floor_validation():
    try:
        simulate_shot([-4.57, -1.0, 0.0], [4.7, 5.8, 0.0], DEFAULT_BACKSPIN_RAD_S)
        raise AssertionError("出手点 y<0 应触发 ValueError")
    except ValueError:
        pass


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as e:                      # noqa: BLE001
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} 通过")
