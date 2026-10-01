"""Element geometry in any shape, platform roles, disabled controls, 8-bit frames, minimized windows, focus waits.

Elements with ``bounds`` or without a size raised ``KeyError``; two equal
zero-area boxes did not match, so an unchanged frame read as a change; only
UIA role names were interactive, so Linux and macOS trees had no tab order or
observation; ``Tab`` was shown visiting disabled controls; 16-bit and float
frames gave wrong quality metrics or raised ``cv2.error``; a minimized window
answered an off-screen client point; a NaN focus-wait timeout never ended.
"""
import sys

import numpy as np
import pytest
from PIL import Image

from je_auto_control.utils.accessibility.element import AccessibilityElement
from je_auto_control.utils.exception.exceptions import AutoControlException


# --- geometry and IoU ---------------------------------------------------------------

def test_elements_in_any_shape_are_placed_and_equal_zero_boxes_match():
    from je_auto_control.utils.action_effect import classify_effect, is_no_op
    from je_auto_control.utils.element_parse import fuse_elements, iou
    placeholder = [{"role": "button", "name": "OK", "x": 0, "y": 0}]
    assert classify_effect(placeholder, [dict(e) for e in placeholder], {"x": 50, "y": 50}).effect == "no_op"
    hidden = [{"role": "button", "name": "Hidden", "x": 0, "y": 0, "width": 0, "height": 0}]
    assert is_no_op(hidden, [dict(e) for e in hidden])
    assert iou({"bounds": [10, 10, 20, 20]}, {"x": 10, "y": 10, "width": 20, "height": 20}) == 1.0
    element = AccessibilityElement(name="Save", role="Button", bounds=(5, 5, 40, 20))
    assert fuse_elements(a11y_boxes=[element.to_dict()])


def test_an_action_without_a_coordinate_and_a_circular_radius():
    from je_auto_control.utils.action_effect import classify_effect, effect_near_point
    before = []
    after = [{"role": "button", "name": "New", "x": 40, "y": 40, "width": 20, "height": 20}]
    assert classify_effect(before, after, {"x": None, "y": None}).effect == "changed"
    assert not effect_near_point(before, after, [0, 0], radius=60)     # 70.7 px away
    assert effect_near_point(before, after, [0, 0], radius=71)


# --- roles and focus --------------------------------------------------------------------

@pytest.mark.parametrize("role", ["Button", "RadioButton", "Hyperlink", "TabItem", "TreeItem", "SplitButton",
                                  "ControlType_50000", 50005, "push button", "check box", "entry",
                                  "AXButton", "AXTextField", "textbox"])
def test_interactive_roles_in_every_spelling(role):
    from je_auto_control.utils.focus_order import is_interactive_role
    from je_auto_control.utils.observation import flatten_tree
    assert is_interactive_role(role)
    assert flatten_tree([{"role": role, "name": "x", "x": 0, "y": 0, "width": 5, "height": 5}])


@pytest.mark.parametrize("role", ["Text", "Pane", "AXStaticText", "label", "Window", "AXApplication"])
def test_static_roles_are_not_interactive(role):
    from je_auto_control.utils.focus_order import is_interactive_role
    assert not is_interactive_role(role)


def test_tab_skips_disabled_controls_and_the_viewport_edge_is_exclusive():
    from je_auto_control.utils.focus_order import audit_focus_order, tab_order
    from je_auto_control.utils.observation import observation_index
    elements = [AccessibilityElement("Name", "Edit", (0, 0, 100, 20)),
                AccessibilityElement("Submit", "Button", (0, 40, 100, 20), enabled=False),
                AccessibilityElement("Cancel", "push button", (0, 80, 100, 20))]
    assert [element.name for element in tab_order(elements)] == ["Name", "Cancel"]
    assert audit_focus_order(elements)["focusable_count"] == 2
    edge = [{"role": "button", "name": "next", "x": 1910, "y": 0, "width": 20, "height": 20}]
    assert observation_index(edge, viewport=[0, 0, 1920, 1080]) == []


# --- 8-bit frames ---------------------------------------------------------------------------

def _square(value, dtype, size=100):
    frame = np.zeros((size, size), dtype)
    frame[40:60, 40:60] = value
    return frame


@pytest.mark.parametrize("frame", [
    np.full((64, 64), 32768, np.uint16),
    np.full((64, 64), 0.5, np.float32),
    Image.fromarray(np.full((64, 64), 32768, np.uint16)),
    Image.fromarray(np.full((64, 64), 0.5, np.float32)),
])
def test_quality_of_sixteen_bit_and_float_frames_is_measured_in_eight_bits(frame):
    from je_auto_control.utils.image_quality import image_quality
    assert 120 <= image_quality(frame)["brightness"] <= 135


@pytest.mark.parametrize("dtype, value", [(np.uint16, 40000), (np.float32, 0.8)])
def test_motion_in_sixteen_bit_and_float_frames(dtype, value):
    from je_auto_control.utils.motion_regions import activity_score, changed_regions
    before, after = _square(0, dtype), _square(value, dtype)
    assert changed_regions(before, after, min_area=50)
    assert activity_score(before, after) > 0.03
    small = _square(100, np.uint16)                       # 0.4 in 8-bit terms: no motion
    assert activity_score(_square(0, np.uint16), small) == 0.0


def test_opencv_errors_in_quality_and_motion_are_framework_errors(monkeypatch):
    import cv2

    from je_auto_control.utils.image_quality import image_quality

    def broken(*_args, **_kwargs):
        raise cv2.error("bad input")

    monkeypatch.setattr(cv2, "Laplacian", broken)
    with pytest.raises(AutoControlException):
        image_quality(np.zeros((8, 8), np.uint8))


# --- windows and focus waits -------------------------------------------------------------------------

def test_a_minimized_window_has_no_client_point(monkeypatch):
    wintypes = pytest.importorskip("ctypes.wintypes", exc_type=(ImportError, ValueError))
    import ctypes

    from je_auto_control.utils.window_geometry import window_geometry
    from je_auto_control.wrapper import auto_control_window

    class _User32:
        iconic = True

        def IsIconic(self, _hwnd):
            return self.iconic

        def GetClientRect(self, _hwnd, rect):
            rect._obj.right, rect._obj.bottom = 200, 100
            return 1

        def ClientToScreen(self, _hwnd, point):
            point._obj.x, point._obj.y = 300, 400
            return 1

    user32 = _User32()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", type("W", (), {"user32": user32})(), raising=False)
    monkeypatch.setattr(auto_control_window, "find_window", lambda _title: (123, "t"))
    assert window_geometry.client_point("t", 10, 10) is None
    user32.iconic = False
    assert window_geometry.client_point("t", 10, 10) == (310, 410)
    assert wintypes


def test_a_nan_focus_wait_is_refused_and_negative_looks_once(monkeypatch):
    from je_auto_control.utils import ax_events
    from je_auto_control.utils.accessibility import backends
    seen = []
    fake = type("B", (), {"wait_for_focus_change": lambda self, timeout: seen.append(timeout)})()
    monkeypatch.setattr(backends, "get_backend", lambda: fake)
    with pytest.raises(ValueError):
        ax_events.wait_for_focus_change(timeout=float("nan"))
    ax_events.wait_for_focus_change(timeout=-5)
    assert seen == [0.0]
