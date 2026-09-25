"""Semantic recording, media assertions, preprocessing, the HTML report and D-Bus (fakes only).

Replay moved a click on an unnamed icon to another button and a hidden match to
(0, 0); enrichment stopped its walk before the clicked control and anchored on
the window; a failed heal escaped replay(); OpenCV errors from video regions
and 16-bit or odd-shaped images escaped the executor; 16-bit scans came out
black; the report took quadratic time; D-Bus kept escapes in socket paths and
let struct errors and malformed signatures out.
"""
import time

import numpy as np
import pytest

from je_auto_control.utils.accessibility import accessibility_api
from je_auto_control.utils.accessibility.element import AccessibilityElement
from je_auto_control.utils.exception.exceptions import AutoControlException


class _Backend:
    name, available = "fake", True

    def __init__(self, tree):
        self.tree = tree

    def list_elements(self, app_name=None, max_results=200, **_kwargs):
        return list(self.tree[:max_results])     # walks stop at max_results, as the real ones do


@pytest.fixture()
def tree(monkeypatch):
    holder = []
    monkeypatch.setattr(accessibility_api, "get_backend", lambda: _Backend(holder))
    return holder


_WINDOW = AccessibilityElement("Editor", "window", (0, 0, 1000, 800), app_name="App")


# --- semantic recording --------------------------------------------------------------------------------

def test_a_control_deep_in_the_tree_is_the_anchor_not_the_window(tree):
    from je_auto_control.utils.semantic_recording import enrich_action
    labels = [AccessibilityElement(f"L{i}", "text", (900, 700, 5, 5), app_name="App") for i in range(248)]
    tree.extend([_WINDOW, *labels, AccessibilityElement("Save", "button", (500, 500, 60, 20), app_name="App")])
    assert enrich_action({"action": "mouse_click", "x": 510, "y": 505})["anchor"]["name"] == "Save"
    assert "anchor" not in enrich_action({"action": "mouse_click", "x": 100, "y": 100})


def test_an_unnamed_or_hidden_match_does_not_relocate(tree):
    from je_auto_control.utils.semantic_recording import relocate_action
    tree.extend([_WINDOW, AccessibilityElement("Close", "button", (960, 0, 40, 20), app_name="App"),
                 AccessibilityElement("Save", "button", (0, 0, 0, 0), app_name="App")])
    unnamed = {"action": "mouse_click", "x": 505, "y": 505,
               "anchor": {"kind": "a11y", "role": "button", "name": "", "app_name": "App"}}
    hidden = {**unnamed, "anchor": {**unnamed["anchor"], "name": "Save"}}
    for action in (unnamed, hidden):
        moved = relocate_action(action)
        assert (moved["x"], moved["y"], moved["relocated"]) == (505, 505, False)


@pytest.mark.parametrize("locate", [
    lambda _d: (_ for _ in ()).throw(AutoControlException("model endpoint timed out")),
    lambda _d: (float("nan"), 3),
])
def test_a_failed_heal_is_a_failed_step_not_an_escape(locate):
    from je_auto_control.utils.semantic_recording import SelfHealingReplayer

    def execute(action):
        if action["x"] == 10:
            raise RuntimeError("element not there")
        return True

    result = SelfHealingReplayer(execute, vlm_locate=locate).replay(
        [{"action": "mouse_click", "x": 1, "y": 1},
         {"action": "mouse_click", "x": 10, "y": 20, "anchor": {"role": "button", "name": "Login"}}])
    assert [step.success for step in result.steps] == [True, False]
    assert result.steps[1].last_error.startswith("heal failed")


# --- media and preprocessing --------------------------------------------------------------------------------

def _clip(path, frames=6):
    import cv2
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    try:
        for index in range(frames):
            writer.write(np.full((48, 64, 3), index * 30, np.uint8))
    finally:
        writer.release()
    return str(path)


def test_video_motion_streams_and_refuses_an_off_frame_region(tmp_path):
    from je_auto_control.utils.executor.action_executor import execute_action
    from je_auto_control.utils.media_assert.media import video_segment_motion
    clip = _clip(tmp_path / "clip.avi")
    assert video_segment_motion(clip) == pytest.approx(30.0, abs=3.0)
    assert video_segment_motion(clip, region=[-10, -10, 20, 20]) == pytest.approx(30.0, abs=3.0)
    with pytest.raises(ValueError, match="outside"):
        video_segment_motion(clip, region=[400, 300, 500, 400])
    record = execute_action([["AC_assert_video_changes", {"video_path": clip, "region": [400, 300, 500, 400],
                                                           "raise_on_fail": False}]])
    assert "outside" in str(record)


def test_sixteen_bit_and_odd_shaped_images_are_processed():
    from je_auto_control.utils.preprocess.preprocess import (
        binarize, enhance_contrast, preprocess_image, to_grayscale,
    )
    scan = np.zeros((40, 60), np.uint16)
    scan[:, 30:] = 60000
    result = preprocess_image(scan, steps=("grayscale", "binarize"))
    assert result.dtype == np.uint8 and result.max() == 255 and result[:, :30].max() == 0
    assert binarize(scan, method="adaptive_gaussian").dtype == np.uint8
    assert to_grayscale(np.zeros((10, 10, 1), np.uint8)).shape == (10, 10)
    assert binarize(np.random.rand(20, 20, 3).astype(np.float32)).dtype == np.uint8
    assert preprocess_image(np.zeros((20, 20), np.uint8), steps="grayscale, contrast").shape == (20, 20)
    with pytest.raises(ValueError, match="block_size"):
        binarize(np.zeros((20, 20), np.uint8), method="adaptive_mean", block_size=1)
    with pytest.raises(ValueError, match="grid"):
        enhance_contrast(np.zeros((20, 20), np.uint8), grid=0)


# --- the HTML report and D-Bus ------------------------------------------------------------------------------------

def test_a_large_report_is_built_in_linear_time(monkeypatch):
    from je_auto_control.utils.generate_report import generate_html_report
    record = {"function_name": "AC_x", "local_param": "p", "time": "t", "program_exception": "None"}
    monkeypatch.setattr(generate_html_report.test_record_instance, "test_record_list", [record] * 20000)
    started = time.monotonic()
    html = generate_html_report.generate_html()
    assert html.count("AC_x") == 20000
    assert time.monotonic() - started < 15      # quadratic: about 70 s for 20,000 records


def test_dbus_addresses_are_unescaped_and_bad_values_are_dbus_errors():
    from je_auto_control.utils.dbus_client import session_bus
    assert session_bus._socket_target("unix:path=/run/bus-for-%3A0") == ("/run/bus-for-:0", False)
    assert session_bus._socket_target("unix:abstract=/tmp/dbus%2dABC") == ("/tmp/dbus-ABC", True)
    for signature, value in (("u", -1), ("i", 2 ** 31), ("y", 300), ("(i", (1,)), ("a", [])):
        with pytest.raises(session_bus.DBusError):
            session_bus._Writer().value(signature, value)
