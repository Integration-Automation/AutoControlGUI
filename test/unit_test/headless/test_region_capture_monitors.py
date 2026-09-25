"""A [left, top, right, bottom] region on a monitor left of the primary is captured, not black.

Pillow's ``ImageGrab.grab(bbox=...)`` on Windows captures the primary monitor
only and crops that, so every region command reading through
``pil_screenshot`` measured black off the primary monitor. ``_Desktop``
behaves as Pillow does there: a primary monitor at (0, 0) and a second one to
its left, holding a red block at (-1900, 10) to (-1800, 60).
"""
import base64
import io
import sys

import numpy as np
import pytest
from PIL import Image

from je_auto_control.utils.color_region import color_region
from je_auto_control.utils.cv2_utils import blobs, region_capture, screenshot
from je_auto_control.utils.exception.exceptions import AutoControlScreenException
from je_auto_control.utils.executor import action_executor
from je_auto_control.utils.hsv_segment import hsv_segment
from je_auto_control.utils.mcp_server.tools import _handlers_screen
from je_auto_control.utils.monitor_layout import logical_frame
from je_auto_control.utils.smart_waits import waits
from je_auto_control.utils.ssim import ssim
from je_auto_control.utils.vision import vlm_api

_LEFT_MONITOR = [-1920, 0, -1720, 100]
_RED = (255, 0, 0)


class _Desktop:
    """``ImageGrab`` as on Windows: a bbox crops the primary monitor, ``all_screens`` spans both."""

    def __init__(self, colour=_RED):
        self.image = Image.new("RGB", (3840, 1080), (255, 255, 255))
        self.image.paste(colour, (20, 10, 120, 60))

    def grab(self, bbox=None, all_screens=False, **_kwargs):
        image, (x0, y0) = (self.image, (-1920, 0)) if all_screens else (self.image.crop((1920, 0, 3840, 1080)), (0, 0))
        if bbox:
            left, top, right, bottom = bbox
            image = image.crop((left - x0, top - y0, right - x0, bottom - y0))
        return image.copy()


def _metrics(index):
    return {76: -1920, 77: 0, 78: 3840, 79: 1080}[index]


@pytest.fixture
def desktop(monkeypatch):
    """Windows with a monitor left of the primary one; returns a setter for the desktop's block colour."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(logical_frame, "_system_metrics", _metrics)

    def show(colour=_RED):
        grabber = _Desktop(colour)
        monkeypatch.setattr(logical_frame, "_load_image_grab", lambda: grabber)
        monkeypatch.setattr(screenshot, "image_grabber", lambda: grabber)

    show()
    return show


def _has_red(image):
    array = np.asarray(image.convert("RGB"))
    return bool(((array[..., 0] > 200) & (array[..., 1] < 50)).any())


def test_a_region_on_the_left_monitor_is_captured(desktop):
    assert _has_red(region_capture.grab_screen_region(_LEFT_MONITOR))
    with pytest.raises(AutoControlScreenException):
        region_capture.grab_screen_region([10, 10, 10, 20])


def test_colour_blobs_are_found_there_in_screen_coordinates(desktop):
    [box] = color_region.find_color_regions(list(_RED), region=_LEFT_MONITOR)
    assert (box["x"], box["y"], box["width"], box["height"]) == (-1900, 10, 100, 50)
    assert box["center"] == [-1851, 34]
    [hsv_box] = hsv_segment.segment_hsv(region=_LEFT_MONITOR, lower_hsv=[0, 200, 200], upper_hsv=[5, 255, 255])
    assert (hsv_box["x"], hsv_box["y"]) == (-1900, 10)
    [hue_box] = hsv_segment.dominant_hue_regions(region=_LEFT_MONITOR, hue=0)
    assert (hue_box["x"], hue_box["y"]) == (-1900, 10)


def test_a_supplied_image_keeps_its_own_coordinates():
    haystack = np.full((100, 200, 3), 255, np.uint8)
    haystack[10:60, 20:120] = _RED
    [box] = color_region.find_color_regions(list(_RED), haystack=haystack, region=_LEFT_MONITOR)
    assert (box["x"], box["y"]) == (20, 10)


def test_ssim_and_the_colour_wait_see_the_left_monitor(desktop):
    reference = _Desktop().image.crop((0, 0, 200, 100))
    assert ssim.ssim_compare(reference, region=_LEFT_MONITOR) == 1.0
    assert waits.wait_until_color(region=[-1900, 10, -1800, 60], target_rgb=list(_RED),
                                  timeout_s=0.5, poll_interval_s=0.05).succeeded


def test_the_stability_token_changes_when_a_target_there_changes(desktop):
    red = action_executor._region_pixel_token((-1900, 10, 100, 50))
    desktop((0, 0, 255))
    assert action_executor._region_pixel_token((-1900, 10, 100, 50)) != red


def test_the_vlm_and_the_mcp_screenshot_see_the_left_monitor(desktop):
    assert _has_red(Image.open(io.BytesIO(vlm_api._capture_screenshot_bytes(_LEFT_MONITOR))))
    [block] = _handlers_screen.screenshot(screen_region=_LEFT_MONITOR)[:1]
    assert _has_red(Image.open(io.BytesIO(base64.b64decode(block.to_dict()["data"]))))


def test_other_platforms_keep_pil_screenshot(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(screenshot, "pil_screenshot",
                        lambda screen_region=None: calls.append(screen_region) or Image.new("RGB", (2, 2)))
    monkeypatch.setattr(logical_frame, "grab_logical", lambda *_a, **_k: pytest.fail("grab_logical used off Windows"))
    region_capture.grab_screen_region([-1920, 0, -1720, 100])
    region_capture.grab_screen_region(None)
    assert calls == [[-1920, 0, -1720, 100], None]


def test_connected_boxes_add_the_origin():
    mask = np.zeros((20, 20), np.uint8)
    mask[2:6, 3:9] = 255
    [box] = blobs.connected_boxes(mask, origin=(-100, 50))
    assert (box["x"], box["y"], box["width"], box["height"]) == (-97, 52, 6, 4)
    assert blobs.connected_boxes(mask)[0]["x"] == 3
