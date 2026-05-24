"""Pure-Python automation primitives that the pytest plugin / BDD
steps wrap. Each function maps one BDD keyword to one AutoControl
wrapper call, so the same surface backs ``Given / When / Then``
steps, ``@pytest.mark.autocontrol`` fixtures, and plain pytest
tests that just want a one-line helper.
"""
from __future__ import annotations

from typing import Optional, Tuple


def keyword_click_image(image_path: str,
                        button: str = "mouse_left",
                        detect_threshold: float = 0.9) -> Tuple[int, int]:
    """Locate ``image_path`` and click its center. Returns the click point."""
    from je_auto_control.wrapper.auto_control_image import locate_and_click
    return locate_and_click(
        image_path, mouse_keycode=button,
        detect_threshold=float(detect_threshold),
    )


def keyword_type_text(text: str) -> None:
    """Type ``text`` into the focused window via the OS keyboard backend."""
    from je_auto_control.wrapper.auto_control_keyboard import write
    write(text)


def keyword_press_key(keycode: str) -> None:
    """Press + release one key by its keycode-table name (e.g. ``enter``)."""
    from je_auto_control.wrapper.auto_control_keyboard import type_keyboard
    type_keyboard(keycode)


def keyword_screenshot(path: str,
                        region: Optional[list] = None) -> str:
    """Capture the screen (or ``region``) to ``path``; returns the path."""
    from je_auto_control.wrapper.auto_control_screen import screenshot
    screenshot(file_path=path, screen_region=region)
    return path


def keyword_screen_size() -> Tuple[int, int]:
    from je_auto_control.wrapper.auto_control_screen import screen_size
    width, height = screen_size()
    return int(width), int(height)


def keyword_wait_for_image(image_path: str,
                           timeout: float = 10.0,
                           detect_threshold: float = 0.9) -> Tuple[int, int]:
    """Block until ``image_path`` appears on screen; raises on timeout."""
    import time
    from je_auto_control.utils.exception.exceptions import (
        ImageNotFoundException,
    )
    from je_auto_control.wrapper.auto_control_image import locate_image_center
    deadline = time.monotonic() + float(timeout)
    last_error: Optional[BaseException] = None
    while time.monotonic() < deadline:
        try:
            return locate_image_center(
                image_path, detect_threshold=float(detect_threshold),
            )
        except ImageNotFoundException as exc:
            last_error = exc
            time.sleep(0.25)
    raise TimeoutError(
        f"image {image_path!r} did not appear in {timeout}s "
        f"(last error: {last_error})",
    )


def keyword_wait_for_text(text: str,
                          timeout: float = 10.0,
                          region: Optional[list] = None) -> Tuple[int, int]:
    """Block until ``text`` is rendered on screen via OCR."""
    from je_auto_control.utils.ocr.ocr_engine import wait_for_text
    return wait_for_text(text, timeout=float(timeout), region=region)


__all__ = [
    "keyword_click_image", "keyword_press_key", "keyword_screen_size",
    "keyword_screenshot", "keyword_type_text", "keyword_wait_for_image",
    "keyword_wait_for_text",
]
