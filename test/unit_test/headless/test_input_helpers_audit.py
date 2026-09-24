"""Input-helper defects from the 2026-09-24 audit (no real input is sent).

Replayed wheel-up scrolled down on X11 and Wayland, where a positive value
defaults to ``scroll_down``; the cleanup release after a failed step went to
``(0, 0)``; waypoints were truncated rather than rounded; and a NaN hold
duration pressed the key before failing.
"""
import pytest

from je_auto_control.utils.input_macro import input_macro
from je_auto_control.utils.key_hold.key_hold import plan_key_hold
from je_auto_control.utils.mouse_path.mouse_path import plan_path
from je_auto_control.wrapper import auto_control_mouse


@pytest.fixture
def mouse(monkeypatch):
    calls = []
    monkeypatch.setattr(auto_control_mouse, "set_mouse_position",
                        lambda x, y: calls.append(("move", x, y)))
    monkeypatch.setattr(auto_control_mouse, "press_mouse",
                        lambda button, x=None, y=None: calls.append(("press", button, x, y)))
    monkeypatch.setattr(auto_control_mouse, "release_mouse",
                        lambda button, x=None, y=None: calls.append(("release", button, x, y)))
    monkeypatch.setattr(auto_control_mouse, "mouse_scroll",
                        lambda value, x=None, y=None, scroll_direction="scroll_down":
                        calls.append(("scroll", value, scroll_direction)))
    return calls


def test_replayed_scroll_names_its_direction(mouse):
    input_macro.replay_timeline([{"op": "scroll", "delta": 2}], sleep=lambda _s: None)
    assert ("scroll", 2, "scroll_up") in mouse


def test_the_cleanup_release_stays_where_the_button_went_down(mouse):
    with pytest.raises(Exception):
        input_macro.replay_timeline(
            [{"op": "mouse_down", "button": "left", "x": 800, "y": 600}, {"op": "bogus"}],
            sleep=lambda _s: None)
    releases = [call for call in mouse if call[0] == "release"]
    assert releases == [("release", "mouse_left", None, None)]


def test_waypoints_round_to_the_nearest_pixel():
    assert plan_path([[-0.6, 10.9]]) == [[-1, 11]]
    path = plan_path([[100.7, -1.7], [200.2, 5.4]], per_segment_steps=2)
    assert path[0] == [101, -2] and path[-1] == [200, 5]


@pytest.mark.parametrize("duration, rate", [(float("nan"), None), (float("inf"), None),
                                            (1.0, float("nan")), (1.0, float("inf"))])
def test_a_non_finite_hold_is_refused_before_any_key_goes_down(duration, rate):
    with pytest.raises(ValueError):
        plan_key_hold("a", duration, rate_hz=rate)
