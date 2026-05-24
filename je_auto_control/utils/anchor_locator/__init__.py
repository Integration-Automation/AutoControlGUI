"""Anchor-based locator: spatial composition of image / OCR / VLM / a11y.

Public surface::

    from je_auto_control import (
        anchor_locate, AnchorOutcome,
        image_locator, ocr_locator, vlm_locator, a11y_locator,
    )

Example: click the green Submit button that sits *below* the Username
label::

    outcome = anchor_locate(
        anchor=ocr_locator("Username"),
        target=image_locator("submit_green.png"),
        relation="below",
    )
    if outcome.found:
        ac.click_mouse("mouse_left", *outcome.target_coords)
"""
from je_auto_control.utils.anchor_locator.locator import (
    AnchorLocatorError, AnchorOutcome, KIND_A11Y, KIND_IMAGE,
    KIND_OCR, KIND_VLM, Locator, REL_ABOVE, REL_BELOW,
    REL_LEFT_OF, REL_NEAR, REL_RIGHT_OF,
    a11y_locator, anchor_locate, image_locator, ocr_locator,
    vlm_locator,
)


__all__ = [
    "AnchorLocatorError", "AnchorOutcome", "KIND_A11Y", "KIND_IMAGE",
    "KIND_OCR", "KIND_VLM", "Locator", "REL_ABOVE", "REL_BELOW",
    "REL_LEFT_OF", "REL_NEAR", "REL_RIGHT_OF",
    "a11y_locator", "anchor_locate", "image_locator", "ocr_locator",
    "vlm_locator",
]
