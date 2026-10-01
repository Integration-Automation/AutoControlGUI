"""Public VLM-locator API.

Locate UI elements by natural-language description using a
vision-language model, as a fallback for cases where pixel templates
and accessibility lookups both come up empty. The backend is chosen
per :mod:`je_auto_control.utils.vision.backends` by env vars.
"""
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from je_auto_control.utils.vision.backends import get_backend
from je_auto_control.utils.vision.backends.base import (
    VLMBackend, VLMNotAvailableError,
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
    if not bound.available:
        raise VLMNotAvailableError(
            "no VLM backend configured; set ANTHROPIC_API_KEY or "
            "OPENAI_API_KEY and install the matching SDK",
        )
    image_bytes = _capture_screenshot_bytes(screen_region)
    coords = bound.locate(image_bytes, description, model=model)
    if coords is None:
        return None
    return _to_screen(coords, image_bytes, screen_region)


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
    if not description or not description.strip():
        raise ValueError("description must be a non-empty string")
    bound = backend if backend is not None else get_backend()
    if not bound.available:
        raise VLMNotAvailableError(
            "no VLM backend configured; set ANTHROPIC_API_KEY or "
            "OPENAI_API_KEY and install the matching SDK",
        )
    image_bytes = _capture_screenshot_bytes(screen_region)
    return bool(bound.verify(image_bytes, description, model=model))


_PNG_SIGNATURE = bytes.fromhex("89504e470d0a1a0a")


def _png_size(data: bytes) -> Optional[Tuple[int, int]]:
    """Width and height from a PNG's IHDR chunk, or None for anything else."""
    if len(data) < 24 or not data.startswith(_PNG_SIGNATURE):
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _capture_screenshot_bytes(
        screen_region: Optional[List[int]] = None) -> bytes:
    """Take a screenshot (optionally of ``[left, top, right, bottom]``, on any monitor) as PNG bytes."""
    fd, tmp = tempfile.mkstemp(prefix="vlm_", suffix=".png")
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        from je_auto_control.utils.cv2_utils.region_capture import grab_screen_region
        grab_screen_region(screen_region).save(str(tmp_path), format="PNG")
        return tmp_path.read_bytes()
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


__all__ = [
    "VLMNotAvailableError", "locate_by_description", "click_by_description",
    "verify_description",
]
