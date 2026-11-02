"""Public VLM-locator API.

Locate UI elements by natural-language description using a
vision-language model, as a fallback for cases where pixel templates
and accessibility lookups both come up empty. The backend is chosen
per :mod:`je_auto_control.utils.vision.backends` by env vars.
"""
from dataclasses import dataclass
from hashlib import sha256
from typing import List, Optional, Tuple

from je_auto_control.utils.vision.backends import get_backend
from je_auto_control.utils.cv2_utils.locator_frame import (
    LocatorFrame, LocatorFrameOwner, current_locator_frame, provided_locator_frame,
)
from je_auto_control.utils.vision.frame_capture import capture_png, capture_with_geometry
from je_auto_control.utils.vision.backends.base import (
    VLMBackend, VLMNotAvailableError, VLMRequestError,
)


def locate_by_description(description: str,
                          screen_region: Optional[List[int]] = None,
                          model: Optional[str] = None,
                          backend: Optional[VLMBackend] = None,
                          ) -> Optional[Tuple[int, int]]:
    """Ask a VLM where ``description`` is on screen; return ``(x, y)`` or None.

    ``screen_region`` is ``[x1, y1, x2, y2]`` in screen pixels. When
    supplied, only that region is sent to the model and the returned
    coordinates are translated back into absolute screen space so
    callers can feed them straight into mouse operations. Raises
    :class:`VLMNotAvailableError` if no backend is configured.
    """
    if not description or not description.strip():
        raise ValueError("description must be a non-empty string")
    bound = backend if backend is not None else get_backend()
    owner = current_locator_frame()
    if owner is not None:
        model = _record_backend(owner, bound, model)
    if not bound.available:
        raise VLMNotAvailableError(
            "no VLM backend configured; set ANTHROPIC_API_KEY or "
            "OPENAI_API_KEY and install the matching SDK",
        )
    frame: Optional[LocatorFrame]
    if owner is not None:
        frame = owner.snapshot()
        image_bytes = frame.png
    else:
        image_bytes, frame = capture_with_geometry(_capture_screenshot_bytes, screen_region)
    coords = bound.locate(image_bytes, description, model=model)
    if coords is None:
        return None
    return frame.to_screen(coords) if frame is not None else _to_screen(coords, image_bytes, screen_region)


def _record_backend(owner: LocatorFrameOwner, bound: VLMBackend, model: Optional[str]) -> Optional[str]:
    chosen = _resolved_model(bound, model)
    owner.record_backend(getattr(bound, "name", type(bound).__name__), chosen)
    return chosen


def _resolved_model(bound: VLMBackend, model: Optional[str]) -> Optional[str]:
    resolver = getattr(bound, "resolve_model", None)
    return resolver(model) if callable(resolver) else model


def _to_screen(coords: Tuple[int, int], image_bytes: bytes,
               screen_region: Optional[List[int]]) -> Optional[Tuple[int, int]]:
    """Check a reply lies on the captured image and translate it to screen space."""
    x, y = coords
    size = _png_size(image_bytes)
    if size is not None and not _inside(x, y, size[0], size[1]):
        # Off the captured image, so not a location either; with no region
        # this reply went straight to the mouse.
        return None
    if screen_region is None:
        return (int(x), int(y))
    # A reply outside the region is a misread, not a location: it was
    # translated and clicked anyway (region 100x100 -> a point at y=5100).
    left, top = int(screen_region[0]), int(screen_region[1])
    if not _inside(x, y, int(screen_region[2]) - left, int(screen_region[3]) - top):
        return None
    return (int(x) + left, int(y) + top)


def _inside(x: int, y: int, width: int, height: int) -> bool:
    """Whether ``(x, y)`` lies within a ``width`` x ``height`` image."""
    return 0 <= x < width and 0 <= y < height


def click_by_description(description: str,
                         screen_region: Optional[List[int]] = None,
                         model: Optional[str] = None,
                         backend: Optional[VLMBackend] = None,
                         ) -> bool:
    """Locate by description, then click the center of the match.

    Returns ``True`` on a successful click, ``False`` if no element was
    found. Raises :class:`VLMNotAvailableError` when no backend exists.
    """
    coords = locate_by_description(
        description, screen_region=screen_region,
        model=model, backend=backend,
    )
    if coords is None:
        return False
    cx, cy = coords
    # pylint: disable-next=import-outside-toplevel  # reason: native input initializes only for an explicit click
    from je_auto_control.wrapper.auto_control_mouse import (
        click_mouse, set_mouse_position,
    )
    set_mouse_position(cx, cy)
    click_mouse("mouse_left", cx, cy)
    return True


def verify_description(description: str,
                       screen_region: Optional[List[int]] = None,
                       model: Optional[str] = None,
                       backend: Optional[VLMBackend] = None) -> bool:
    """Ask a VLM whether ``description`` is true of the current screen.

    A yes/no companion to :func:`locate_by_description` — useful for
    semantic assertions ("the cart shows three items"). Raises
    :class:`VLMNotAvailableError` if no backend is configured.
    """
    return _verify_snapshot(description, screen_region, model, backend).verified


@dataclass(frozen=True)
class _VerificationSnapshot:
    verified: bool
    frame_hash: str
    backend: str
    model: Optional[str]


def _verify_snapshot(description: str, screen_region: Optional[List[int]] = None,
                      model: Optional[str] = None, backend: Optional[VLMBackend] = None) -> _VerificationSnapshot:
    if not description or not description.strip():
        raise ValueError("description must be a non-empty string")
    bound = backend if backend is not None else get_backend()
    if not bound.available:
        raise VLMNotAvailableError(
            "no VLM backend configured; set ANTHROPIC_API_KEY or "
            "OPENAI_API_KEY and install the matching SDK",
        )
    image_bytes, frame = capture_with_geometry(_capture_screenshot_bytes, screen_region)
    model = _resolved_model(bound, model)
    with provided_locator_frame(frame):
        verified = bound.verify(image_bytes, description, model=model)
    if not isinstance(verified, bool):
        raise VLMRequestError("verification backend must return bool")
    return _VerificationSnapshot(verified, sha256(image_bytes).hexdigest(),
                                  getattr(bound, "name", type(bound).__name__), model)


_PNG_SIGNATURE = bytes.fromhex("89504e470d0a1a0a")


def _png_size(data: bytes) -> Optional[Tuple[int, int]]:
    """Width and height from a PNG's IHDR chunk, or None for anything else."""
    if len(data) < 24 or not data.startswith(_PNG_SIGNATURE):
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _capture_screenshot_bytes(
        screen_region: Optional[List[int]] = None) -> bytes:
    """Read one in-memory logical PNG, reporting geometry to the scoped caller."""
    return capture_png(screen_region)


__all__ = [
    "VLMNotAvailableError", "locate_by_description", "click_by_description",
    "verify_description",
]
