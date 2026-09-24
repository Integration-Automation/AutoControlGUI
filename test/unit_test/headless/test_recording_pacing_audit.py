"""Recorder and iOS lookup defects from the 2026-09-24 audit (fakes only).

Recorders wrote frames as fast as capture allowed while the header declared
``fps``, so playback length was wrong; every frame also recorded an
``AC_screenshot`` action; an unopened VideoWriter (fps 0, NaN, bad codec) was
accepted and spun forever; and iOS ``find_element`` looked the element up a
second time with a 30 s timeout.
"""
import math

import pytest

from je_auto_control.utils.cv2_utils import screen_record
from je_auto_control.utils.cv2_utils.frame_clock import check_fps, record_paced
from je_auto_control.utils.exception.exceptions import AutoControlScreenException


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _paced(fps, capture_seconds, duration):
    clock = _Clock()
    written = []

    def grab():
        clock.now += capture_seconds
        return "frame"

    return record_paced(lambda: clock.now < duration, grab, written.append, fps,
                        clock=clock, sleep=clock.sleep), written


@pytest.mark.parametrize("capture_seconds", [0.001, 0.2])
def test_the_frame_count_follows_wall_time(capture_seconds):
    count, _ = _paced(30, capture_seconds, 2.0)
    assert abs(count - 60) <= 7


@pytest.mark.parametrize("fps", [0, -5, math.nan, math.inf, "fast"])
def test_an_unusable_frame_rate_is_refused(fps):
    with pytest.raises(AutoControlScreenException):
        check_fps(fps)


def test_an_unopened_writer_is_refused(monkeypatch):
    import cv2

    class _Closed:
        fourcc = staticmethod(lambda *_codec: 0)

        def __init__(self, *_args):
            self.released = False

        def isOpened(self):  # noqa: N802 - cv2 name
            return False

        def release(self):
            self.released = True

    monkeypatch.setattr(cv2, "VideoWriter", _Closed)
    with pytest.raises(AutoControlScreenException):
        screen_record.ScreenRecordThread("nodir/x.avi", "XVID", 30, (4, 4))


def test_recording_frames_are_not_recorded_as_screenshot_actions(monkeypatch):
    import numpy as np
    from PIL import Image
    from je_auto_control.utils.cv2_utils import screenshot as screenshot_module
    from je_auto_control.utils.test_record import record_test_class
    records = record_test_class.test_record_instance
    monkeypatch.setattr(records, "init_record", True)
    before = len(records.test_record_list)
    monkeypatch.setattr(screenshot_module, "pil_screenshot",
                        lambda *a, **k: Image.fromarray(np.zeros((4, 4, 3), dtype=np.uint8)))
    thread = object.__new__(screen_record.ScreenRecordThread)
    thread.resolution = (4, 4)
    thread._grab()
    assert len(records.test_record_list) == before


def test_ios_find_uses_the_element_it_waited_for(monkeypatch):
    from je_auto_control.ios import find as ios_find
    bounds = type("Bounds", (), {"x": 10, "y": 20, "width": 30, "height": 40})()

    class _Query:
        def wait(self, timeout):
            return type("Element", (), {"bounds": bounds})()

        @property
        def bounds(self):
            raise AssertionError("looked the element up a second time")

    monkeypatch.setattr(ios_find, "_build_query", lambda *_args: _Query())
    device = type("Device", (), {"handle": object()})()
    assert ios_find.find_element(name="OK", device=device) == (10, 20, 40, 60)
