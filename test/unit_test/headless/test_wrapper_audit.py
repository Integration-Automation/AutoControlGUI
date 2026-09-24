"""Regression tests for the screen / image / input-wrapper defects of the 2026-09-23 audit.

Template matching returned the first position over the threshold in scan order
(1-5 px off the real match), never matched a pixel-identical template at the
default threshold of 1.0, crashed with ``draw_image=True`` on the multi path,
and let a missing template or a threshold outside 0..1 through. Scrolling was
clamped to the primary monitor, and out-of-range integers were truncated by
ctypes -- the wrong point clicked, the wrong key pressed, success reported.
Everything here runs on synthetic frames and recording fakes.
"""
import sys
import types

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("cv2")
pytest.importorskip("je_open_cv")

from je_auto_control.utils.cv2_utils import template_detection  # noqa: E402
from je_auto_control.utils.exception.exceptions import (  # noqa: E402
    AutoControlKeyboardException, AutoControlMouseException, ImageNotFoundException,
)
from je_auto_control.wrapper import auto_control_image, auto_control_keyboard, auto_control_mouse  # noqa: E402

_ORIGIN = (1000, 500)


@pytest.fixture
def screen(monkeypatch):
    """A smooth blob centred at (150, 100) of a 300x200 frame, on screen at _ORIGIN."""
    yy, xx = np.mgrid[0:200, 0:300]
    blob = (255 * np.exp(-(((xx - 150) ** 2) / 400 + ((yy - 100) ** 2) / 300))).astype(np.uint8)
    frame = Image.fromarray(np.stack([blob] * 3, axis=-1))
    monkeypatch.setattr(template_detection, "grab_logical",
                        lambda region, all_screens=True: (frame.copy(), *_ORIGIN))
    return frame


def test_a_pixel_identical_template_matches_at_the_default_threshold(screen):
    template = screen.crop((130, 80, 170, 120))
    assert auto_control_image.locate_image_center(template) == (1150, 600)


@pytest.mark.parametrize("threshold", [0.99, 0.95, 0.9, 0.8])
def test_the_best_match_is_returned_not_the_first_over_the_threshold(screen, threshold):
    template = screen.crop((130, 80, 170, 120))
    assert auto_control_image.locate_image_center(template, threshold) == (1150, 600)


def test_locate_all_with_drawing_returns_the_boxes(screen):
    template = screen.crop((130, 80, 170, 120))
    assert auto_control_image.locate_all_image(template, 0.95, draw_image=True) == [[1130, 580, 1170, 620]]


def test_a_missing_template_file_is_named(screen):
    with pytest.raises(ImageNotFoundException, match="missing.png"):
        auto_control_image.locate_image_center("C:/nope/missing.png")


@pytest.mark.parametrize("threshold", [-1, 85])
def test_a_threshold_outside_zero_to_one_is_refused(screen, threshold):
    with pytest.raises(ImageNotFoundException, match="between 0 and 1"):
        auto_control_image.locate_all_image(screen.crop((130, 80, 170, 120)), threshold)


# --- mouse / keyboard ---------------------------------------------------------

@pytest.fixture
def mouse_moves(monkeypatch):
    moves = []
    backend = types.SimpleNamespace(set_position=lambda x, y: moves.append((x, y)),
                                    scroll=lambda *args: moves.append(("scroll",) + args))
    monkeypatch.setattr(auto_control_mouse, "mouse", backend)
    monkeypatch.setattr(auto_control_mouse, "record_action_to_list", lambda *a, **k: None)
    monkeypatch.setattr(auto_control_mouse, "special_mouse_keys_table", {"scroll_down": 5})
    return moves


@pytest.mark.parametrize("value", ["abc", float("inf"), 2 ** 40, -(2 ** 40)])
def test_an_unusable_coordinate_is_a_mouse_error(mouse_moves, value):
    with pytest.raises(AutoControlMouseException):
        auto_control_mouse.set_mouse_position(value, 5)
    assert mouse_moves == [], "nothing may move"


def test_scrolling_can_reach_a_monitor_left_of_the_primary(mouse_moves, monkeypatch):
    monkeypatch.setattr(auto_control_mouse, "logical_virtual_rect", lambda: (-1920, 0, 3840, 1080))
    monkeypatch.setattr(sys, "platform", "win32")
    auto_control_mouse.mouse_scroll(3, x=-800, y=300)
    auto_control_mouse.mouse_scroll(3, x=2500, y=300)
    assert [move for move in mouse_moves if move[0] != "scroll"] == [(-800, 300), (1919, 300)]


def test_a_keycode_past_a_windows_virtual_key_is_refused(monkeypatch):
    monkeypatch.setattr(auto_control_keyboard, "is_windows", lambda: True)
    with pytest.raises(AutoControlKeyboardException):
        auto_control_keyboard._resolve_keycode(65 + 65536)
    assert auto_control_keyboard._resolve_keycode(65) == 65
