"""Tests for human-like mouse motion (pure path generation + mover)."""
from je_auto_control.utils.humanize.motion import (
    HumanizedMotion, humanized_path, move_mouse_humanized,
)


def test_path_lands_exactly_on_target():
    path = humanized_path((0, 0), (100, 50),
                          HumanizedMotion(steps=20, seed=1))
    assert path[-1] == (100, 50)
    assert len(path) == 20
    assert all(isinstance(x, int) and isinstance(y, int) for x, y in path)


def test_path_is_deterministic_for_a_seed():
    a = humanized_path((0, 0), (300, 120), HumanizedMotion(seed=42))
    b = humanized_path((0, 0), (300, 120), HumanizedMotion(seed=42))
    assert a == b


def test_different_seeds_produce_different_paths():
    a = humanized_path((0, 0), (300, 120), HumanizedMotion(seed=1, jitter=2.0))
    b = humanized_path((0, 0), (300, 120), HumanizedMotion(seed=2, jitter=2.0))
    assert a != b


def test_overshoot_still_settles_on_target():
    path = humanized_path((0, 0), (200, 0),
                          HumanizedMotion(steps=30, overshoot=0.15, seed=7))
    assert path[-1] == (200, 0)
    # Some waypoint must pass beyond the target before settling back.
    assert any(x > 200 for x, _ in path[:-1])


def test_zero_distance_returns_single_point():
    assert humanized_path((10, 10), (10, 10)) == [(10, 10)]


def test_move_mouse_humanized_walks_the_path(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_mouse.get_mouse_position",
        lambda: (0, 0),
    )
    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_mouse.set_mouse_position",
        lambda x, y: calls.append((x, y)),
    )
    slept = []
    path = move_mouse_humanized(
        80, 40, duration_s=0.1,
        motion=HumanizedMotion(steps=10, seed=3),
        sleep=slept.append,
    )
    assert calls == path
    assert calls[-1] == (80, 40)
    assert slept  # the injected sleep was invoked per waypoint
