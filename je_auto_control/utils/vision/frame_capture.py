"""Logical VLM PNG capture with run-local geometry and an injectable byte-reader seam."""
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from je_auto_control.utils.cv2_utils.locator_frame import LocatorFrame, locator_frame_scope
from je_auto_control.utils.vision.backends.base import VLMRequestError


@dataclass
class _CaptureSlot:
    frame: Optional[LocatorFrame] = None


_CAPTURED: ContextVar[Optional[_CaptureSlot]] = ContextVar("je_auto_control_vlm_captured_geometry", default=None)


def capture_png(screen_region: Optional[List[int]]) -> bytes:
    """Capture logical pixels in memory, preserving the actual origin instead of padding."""
    with locator_frame_scope(screen_region, all_screens=False) as owner:
        frame = owner.snapshot()
        slot = _CAPTURED.get()
        if slot is not None:
            slot.frame = frame
        return frame.png


def capture_with_geometry(reader: Callable[[Optional[List[int]]], bytes],
                           region: Optional[List[int]]) -> Tuple[bytes, Optional[LocatorFrame]]:
    """Scope captured geometry to one read; injected legacy readers may supply bytes only."""
    slot = _CaptureSlot()
    token = _CAPTURED.set(slot)
    try:
        data = reader(region)
        if slot.frame is not None and slot.frame.png != data:
            raise VLMRequestError("captured geometry does not belong to the supplied PNG")
        return data, slot.frame
    finally:
        _CAPTURED.reset(token)
