"""MCP adapters for the screen: capture, pixels, image and text search, recording.

Same contract as :mod:`._handlers` -- normalise arguments and return values so
they survive the JSON-RPC boundary, with every project import lazy -- split out
by theme because ``_handlers.py`` is over the 750-line limit.
"""
import base64
import io
import math
import os
from typing import Any, Dict, List, Optional

from je_auto_control.utils.mcp_server.tools._base import MCPContent
from je_auto_control.utils.timeouts import clamp_poll_interval, deadline_after


# === Screen / image / OCR ===================================================

def screen_size() -> List[int]:
    from je_auto_control.wrapper.auto_control_screen import screen_size as _size
    width, height = _size()
    return [int(width), int(height)]


def screenshot(file_path: Optional[str] = None,
               screen_region: Optional[List[int]] = None,
               monitor_index: Optional[int] = None,
               ) -> List[MCPContent]:
    """Take a screenshot, optionally save it, and return image + path.

    When ``monitor_index`` is provided, capture that specific monitor
    via ``mss`` (works across multi-display setups). Index 0 is the
    virtual desktop spanning all monitors; 1+ are individual screens.
    """
    saved_path: Optional[str] = None
    if file_path is not None:
        saved_path = os.path.realpath(os.fspath(file_path))
        parent = os.path.dirname(saved_path) or "."
        if not os.path.isdir(parent):
            raise ValueError(f"screenshot directory does not exist: {parent}")
    if monitor_index is not None:
        image = _grab_monitor(int(monitor_index))
        if saved_path is not None:
            image.save(saved_path)
    else:
        from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
        image = pil_screenshot(file_path=saved_path, screen_region=screen_region)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    contents: List[MCPContent] = [MCPContent.image_block(encoded)]
    if saved_path is not None:
        contents.append(MCPContent.text_block(f"saved: {saved_path}"))
    return contents


def list_monitors() -> List[Dict[str, Any]]:
    """Return every monitor's geometry. Index 0 spans all monitors."""
    from je_auto_control.utils.cv2_utils.screen_grabber import mss_grabber
    with mss_grabber() as sct:
        return [
            {
                "index": index, "left": int(monitor["left"]),
                "top": int(monitor["top"]),
                "width": int(monitor["width"]),
                "height": int(monitor["height"]),
                "is_combined": index == 0,
            }
            for index, monitor in enumerate(sct.monitors)
        ]


def _grab_monitor(index: int):
    """Capture a single monitor through the platform grabber; returns a PIL Image."""
    from je_auto_control.utils.cv2_utils.screen_grabber import mss_grabber
    from PIL import Image
    with mss_grabber() as sct:
        if index < 0 or index >= len(sct.monitors):
            raise ValueError(
                f"monitor index {index} out of range "
                f"(0..{len(sct.monitors) - 1})"
            )
        frame = sct.grab(sct.monitors[index])
        return Image.frombytes("RGB", frame.size, frame.bgra, "raw", "BGRX")


def get_pixel(x: int, y: int) -> List[int]:
    from je_auto_control.wrapper.auto_control_screen import get_pixel as _pixel
    pixel = _pixel(int(x), int(y))
    if pixel is None:
        return []
    return [int(component) for component in pixel]


def _matching_channels(raw: Any, target: List[int], tol: int) -> Optional[List[int]]:
    """The pixel's RGB when every channel is within ``tol`` of ``target``, else ``None``."""
    if raw is None or len(raw) < 3:
        return None
    channels = [int(raw[i]) for i in range(3)]
    if all(abs(channels[i] - target[i]) <= tol for i in range(3)):
        return channels
    return None


def _sleep_before(deadline: float, poll_seconds: float) -> bool:
    """Sleep one poll, never past ``deadline``; ``False`` once the deadline has passed."""
    import time as _time
    remaining = deadline - _time.monotonic()
    if remaining <= 0:
        return False
    _time.sleep(min(poll_seconds, remaining))
    return True


def wait_for_image(image_path: str, timeout: float = 10.0,
                   poll: float = 0.5,
                   detect_threshold: float = 1.0,
                   ctx: Any = None) -> List[int]:
    """Poll for ``image_path`` on screen; return its centre [x, y] or raise."""
    import time as _time
    from je_auto_control.utils.exception.exceptions import ImageNotFoundException
    from je_auto_control.wrapper.auto_control_image import locate_image_center as _loc
    poll_seconds = clamp_poll_interval(poll)
    start = _time.monotonic()
    deadline = deadline_after(start, timeout)
    total = float(timeout) if math.isfinite(float(timeout)) else None
    while True:   # probe first: timeout=0 means "look once"
        if ctx is not None:
            ctx.check_cancelled()
            ctx.progress(_time.monotonic() - start, total=total,
                          message=f"waiting for {image_path}")
        try:
            cx, cy = _loc(image_path,
                          detect_threshold=float(detect_threshold))
            return [int(cx), int(cy)]
        except ImageNotFoundException:
            if not _sleep_before(deadline, poll_seconds):
                break
    raise TimeoutError(
        f"wait_for_image timed out after {timeout}s: {image_path!r}"
    )


def wait_for_pixel(x: int, y: int, target_rgb: List[int],
                   tolerance: int = 8, timeout: float = 10.0,
                   poll: float = 0.25,
                   ctx: Any = None) -> List[int]:
    """Poll until pixel ``(x, y)`` matches ``target_rgb`` within ``tolerance``."""
    import time as _time
    from je_auto_control.wrapper.auto_control_screen import get_pixel as _pixel
    if len(target_rgb) < 3:
        raise ValueError("target_rgb must contain at least 3 channels")
    target = [int(c) for c in target_rgb[:3]]
    tol = max(0, int(tolerance))
    poll_seconds = clamp_poll_interval(poll)
    deadline = deadline_after(_time.monotonic(), timeout)
    while True:   # probe first: timeout=0 means "look once"
        if ctx is not None:
            ctx.check_cancelled()
        channels = _matching_channels(_pixel(int(x), int(y)), target, tol)
        if channels is not None:
            return channels
        if not _sleep_before(deadline, poll_seconds):
            break
    raise TimeoutError(
        f"wait_for_pixel timed out after {timeout}s at ({x}, {y})"
    )


def diff_screenshots(image_path_a: str,
                     image_path_b: str,
                     threshold: int = 16,
                     min_box_pixels: int = 25,
                     ) -> Dict[str, Any]:
    """Return the bounding boxes that differ between two screenshots.

    The result is JSON-friendly: ``{"size": [w, h], "boxes": [[x, y, w, h], ...]}``.
    Boxes are merged via a flood-fill so a single changed widget is one
    rectangle. Pixels whose absolute per-channel difference is at most
    ``threshold`` are considered equal; tiny components below
    ``min_box_pixels`` are dropped to ignore JPEG / antialias noise.
    """
    safe_a = os.path.realpath(os.fspath(image_path_a))
    safe_b = os.path.realpath(os.fspath(image_path_b))
    return _diff_screenshots(safe_a, safe_b, int(threshold),
                              int(min_box_pixels))


def _diff_screenshots(path_a: str, path_b: str, threshold: int,
                      min_box_pixels: int) -> Dict[str, Any]:
    """Implementation split off so the public adapter stays under 75 lines."""
    import numpy as np
    from PIL import Image

    img_a = np.asarray(Image.open(path_a).convert("RGB"))
    img_b = np.asarray(Image.open(path_b).convert("RGB"))
    if img_a.shape != img_b.shape:
        height = min(img_a.shape[0], img_b.shape[0])
        width = min(img_a.shape[1], img_b.shape[1])
        img_a = img_a[:height, :width]
        img_b = img_b[:height, :width]
    diff = np.abs(img_a.astype("int16") - img_b.astype("int16"))
    mask = (diff.max(axis=-1) > threshold).astype("uint8")
    boxes = _connected_component_boxes(mask, min_box_pixels)
    height, width = mask.shape
    return {"size": [int(width), int(height)], "boxes": boxes}


def _connected_component_boxes(mask: Any,
                               min_pixels: int) -> List[List[int]]:
    """Return tight bounding boxes for connected non-zero regions in ``mask``."""
    import numpy as np

    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    boxes: List[List[int]] = []
    for start_y in range(height):
        for start_x in range(width):
            if mask[start_y, start_x] == 0 or visited[start_y, start_x]:
                continue
            box = _flood_fill_box(mask, visited, start_x, start_y)
            if box[2] * box[3] < min_pixels:
                continue
            boxes.append(box)
    return boxes


_screen_recorder_singleton: Any = None


def _get_screen_recorder() -> Any:
    """Lazy-init the process-wide ScreenRecorder."""
    global _screen_recorder_singleton
    if _screen_recorder_singleton is None:
        from je_auto_control.utils.cv2_utils.screen_record import ScreenRecorder
        _screen_recorder_singleton = ScreenRecorder()
    return _screen_recorder_singleton


def screen_record_start(recorder_name: str,
                        file_path: str,
                        codec: str = "XVID",
                        frame_per_sec: int = 30,
                        width: int = 1920,
                        height: int = 1080) -> str:
    """Start a screen recording under ``recorder_name``; returns the resolved path."""
    safe_path = os.path.realpath(os.fspath(file_path))
    parent = os.path.dirname(safe_path) or "."
    if not os.path.isdir(parent):
        raise ValueError(f"recording directory does not exist: {parent}")
    recorder = _get_screen_recorder()
    recorder.start_new_record(
        recorder_name=str(recorder_name),
        path_and_filename=safe_path, codec=str(codec),
        frame_per_sec=int(frame_per_sec),
        resolution=(int(width), int(height)),
    )
    return safe_path


def screen_record_stop(recorder_name: str) -> str:
    """Stop the named screen recording; no-op if it doesn't exist."""
    recorder = _get_screen_recorder()
    recorder.stop_record(str(recorder_name))
    return "stopped"


def screen_record_list() -> List[str]:
    """Return the names of currently running recorders."""
    recorder = _get_screen_recorder()
    return sorted(recorder.running_recorder.keys())


def _flood_fill_box(mask: Any, visited: Any,
                    start_x: int, start_y: int) -> List[int]:
    """Iterative 4-connectivity flood fill returning [x, y, w, h]."""
    height, width = mask.shape
    stack = [(start_x, start_y)]
    min_x = max_x = start_x
    min_y = max_y = start_y
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        if visited[y, x] or mask[y, x] == 0:
            continue
        visited[y, x] = True
        min_x, max_x = min(min_x, x), max(max_x, x)
        min_y, max_y = min(min_y, y), max(max_y, y)
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return [int(min_x), int(min_y),
            int(max_x - min_x + 1), int(max_y - min_y + 1)]


def locate_image_center(image_path: str,
                        detect_threshold: float = 1.0) -> List[int]:
    from je_auto_control.wrapper.auto_control_image import locate_image_center as _loc
    cx, cy = _loc(image_path, detect_threshold=float(detect_threshold))
    return [int(cx), int(cy)]


def locate_and_click(image_path: str,
                     mouse_keycode: str = "mouse_left",
                     detect_threshold: float = 1.0) -> List[int]:
    from je_auto_control.wrapper.auto_control_image import locate_and_click as _loc_click
    cx, cy = _loc_click(image_path, mouse_keycode,
                        detect_threshold=float(detect_threshold))
    return [int(cx), int(cy)]


def locate_text(text: str,
                region: Optional[List[int]] = None,
                min_confidence: float = 60.0) -> List[int]:
    from je_auto_control.utils.ocr.ocr_engine import locate_text_center
    cx, cy = locate_text_center(text, region=region,
                                min_confidence=float(min_confidence))
    return [int(cx), int(cy)]


def click_text(text: str,
               mouse_keycode: str = "mouse_left",
               region: Optional[List[int]] = None,
               min_confidence: float = 60.0) -> List[int]:
    from je_auto_control.utils.ocr.ocr_engine import click_text as _click
    cx, cy = _click(text, mouse_keycode=mouse_keycode, region=region,
                    min_confidence=float(min_confidence))
    return [int(cx), int(cy)]
