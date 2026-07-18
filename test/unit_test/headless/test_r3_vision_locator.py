"""R3 regression: anchor not-found handling, directional distance, wma zero-sum.

Covers:
* anchor adapters catching only (OSError, RuntimeError, ValueError), so a plain
  ImageNotFoundException / AutoControlActionException ("not on screen") crashed
  the whole locate instead of returning found=False / [].
* max_distance_px applied only for relation==near, ignored for directional
  relations.
* smoothing.wma dividing by a zero-sum weight window (warm-up tail of [1, 0]).
"""
import pytest

from je_auto_control.utils.anchor_locator import (
    anchor_locate, image_locator, ocr_locator, REL_NEAR,
)
from je_auto_control.utils.anchor_locator import locator as locator_mod
from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, ImageNotFoundException,
)
from je_auto_control.utils.smoothing.smoothing import wma


# --- finding 8: adapters swallow framework "not found" exceptions --------

def test_image_candidates_swallow_not_found(monkeypatch):
    def raise_not_found(*_args, **_kwargs):
        raise ImageNotFoundException("not on screen")

    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_image.locate_all_image",
        raise_not_found,
    )
    assert locator_mod._image_candidates(image_locator("b.png")) == []


def test_ocr_center_swallows_action_exception(monkeypatch):
    def raise_action(*_args, **_kwargs):
        raise AutoControlActionException("text not found")

    monkeypatch.setattr(
        "je_auto_control.utils.ocr.ocr_engine.locate_text_center",
        raise_action,
    )
    assert locator_mod._ocr_center(ocr_locator("Submit")) is None


def test_anchor_locate_target_missing_returns_outcome(monkeypatch):
    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_image.locate_image_center",
        lambda *_a, **_k: (10, 10),          # anchor resolves fine
    )

    def raise_not_found(*_args, **_kwargs):
        raise ImageNotFoundException("no target")

    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_image.locate_all_image",
        raise_not_found,
    )
    outcome = anchor_locate(anchor=image_locator("a.png"),
                            target=image_locator("b.png"), relation=REL_NEAR)
    assert outcome.found is False
    assert outcome.error == "target not found"


# --- finding 9: wma zero-sum weight window -------------------------------

def test_wma_zero_weight_tail_no_zero_division():
    # weights=[1, 0]: the warm-up window is [value0] with applied weight [0].
    assert wma([5.0, 6.0], weights=[1, 0]) == [5.0, 5.0]


def test_wma_normal_case_unaffected():
    out = wma([1.0, 2.0, 3.0], weights=[1, 2])
    assert out[0] == pytest.approx(1.0)
    assert out[1] == pytest.approx((1 * 1 + 2 * 2) / 3)
    assert out[2] == pytest.approx((2 * 1 + 3 * 2) / 3)
