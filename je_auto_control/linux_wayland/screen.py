"""Wayland screen backend (compositor capture tools + wlr-randr).

Everything here funnels through :func:`grab_image`, which is also the hook
the framework's generic capture layer looks for
(:mod:`je_auto_control.utils.cv2_utils.screen_grabber`). That indirection is
the point: Pillow's ``ImageGrab`` and ``mss`` both read the X11 root window
on Linux, and under Wayland that root belongs to XWayland, which does not
composite native Wayland windows. Pillow's own fallback to the same capture
tools only runs when the X11 grab *raises*, which it does not while XWayland
is up; ``mss`` has no fallback at all. Publishing ``grab_image`` here is what
makes locators, OCR, screenshots, recording and remote-desktop frames see the
real screen — and see it the same way regardless of whether XWayland is
running.

Resolution comes from ``wlr-randr`` when it is present and from the capture
itself otherwise, so the call works on GNOME / KDE without extra tools.
"""
from __future__ import annotations

import re
from io import BytesIO
from typing import List, Optional, Sequence, Tuple

from PIL import Image

from je_auto_control.linux_wayland import capture as wayland_capture
from je_auto_control.linux_wayland._detect import WAYLAND_WLR_RANDR, binary_path
from je_auto_control.utils.exception.exceptions import AutoControlScreenException


# Bounded quantifiers (max 5 digits per side, more than enough for any real
# monitor resolution) keep these regexes provably linear-time.
_MODE_RE = re.compile(r"(\d{1,5})x(\d{1,5})")
_POSITION_RE = re.compile(r"^\s*Position:\s*(-?\d{1,5}),(-?\d{1,5})")
_ENABLED_RE = re.compile(r"^\s*Enabled:\s*(\w+)")


def _validate_region(screen_region: Sequence[int]) -> Tuple[int, int, int, int]:
    """Reject a region that would crop to an empty image."""
    try:
        x1, y1, x2, y2 = (int(value) for value in screen_region)
    except (TypeError, ValueError) as error:
        raise AutoControlScreenException(
            f"screen_region must be 4 ints [left, top, right, bottom]; "
            f"got {screen_region!r}",
        ) from error
    if x2 <= x1 or y2 <= y1:
        raise AutoControlScreenException(
            f"screen_region must have positive width and height; got "
            f"[{x1}, {y1}, {x2}, {y2}]",
        )
    return x1, y1, x2, y2


def grab_image(screen_region: Optional[Sequence[int]] = None) -> Image.Image:
    """Capture the screen and return it as an RGB :class:`PIL.Image.Image`.

    ``screen_region`` is ``[left, top, right, bottom]`` — the same bbox
    convention as ``ImageGrab.grab``, so the generic capture layer can hand
    this straight to callers written against Pillow.

    Coordinates are the compositor's layout coordinates, which is what
    ``grim -g`` takes and what ``wlr-randr`` reports positions in. The
    whole-screen capture spans the entire output layout rather than one
    monitor, so its top-left pixel is :func:`layout_origin` — ``(0, 0)``
    only while no output sits left of or above the origin. The crop below
    subtracts that origin; grim applies the region itself and needs no
    help, but every other tier hands back the whole layout.

    :param screen_region: region to capture, or None for the whole layout.
    :return: the captured image, always in RGB mode.
    """
    region = _validate_region(screen_region) if screen_region is not None else None
    captured = wayland_capture.grab_png(region)
    with Image.open(BytesIO(captured.data)) as raw:
        # convert() reads the frame in, so the result outlives the file object.
        image = raw.convert("RGB")
    if region is None or captured.region_applied:
        return image
    origin_x, origin_y = layout_origin()
    x1, y1, x2, y2 = region
    return image.crop((x1 - origin_x, y1 - origin_y,
                       x2 - origin_x, y2 - origin_y))


def size() -> Tuple[int, int]:
    """Return the size of the whole output layout, in pixels.

    Named ``size`` to match the backend contract the wrapper calls
    (``screen.size()``), as the windows / osx / x11 backends all do.

    This is the size of the layout bounding box, not one monitor and not
    its right/bottom edge: it has to agree with :func:`grab_image`, because
    ``get_pixel`` addresses the same coordinate space and the mss-shaped
    shim composes the two into its monitor list. On a layout whose left-most
    output starts at a negative x the two differ — the edge is smaller than
    the width by the origin — and reporting the edge would make every
    consumer of ``size()`` grab a frame narrower than the screen.

    Tries ``wlr-randr`` first (sway / Hyprland) and falls back to measuring
    a capture, so the call still works on GNOME / KDE.

    :return: (width, height)
    """
    coords = _size_from_wlr_randr()
    if coords is not None:
        return coords
    image = grab_image()
    return int(image.width), int(image.height)


def layout_origin() -> Tuple[int, int]:
    """Return the layout coordinate of :func:`grab_image`'s top-left pixel.

    ``(0, 0)`` on a single-monitor layout and on any layout whose outputs
    all sit at non-negative coordinates — but a monitor placed left of or
    above the primary one gives the layout a negative origin, and a capture
    of the whole layout then starts there rather than at the origin of the
    coordinate space.

    Callers that map a position found *in* a frame back to a screen
    coordinate have to add this; :func:`grab_image` subtracts it when it
    crops. ``(0, 0)`` where ``wlr-randr`` cannot say (GNOME / KDE), which
    is also the answer for the layouts it would otherwise report.

    :return: (origin_x, origin_y)
    """
    rects = _wlr_randr_rects()
    if not rects:
        return (0, 0)
    return (min(x for x, _, _, _ in rects), min(y for _, y, _, _ in rects))


def get_pixel(x: int, y: int) -> Tuple[int, int, int]:
    """Return the ``(r, g, b)`` colour at ``(x, y)``.

    Captures a 1x1 region at the point — grim grabs exactly that, and the
    file-based helpers grab the screen and crop. Returns RGB to match the
    x11 / windows / osx backends.

    :param x: X coordinate.
    :param y: Y coordinate.
    :return: (R, G, B)
    """
    image = grab_image([int(x), int(y), int(x) + 1, int(y) + 1])
    return image.getpixel((0, 0))


def screenshot(file_path: Optional[str] = None,
               screen_region: Optional[List[int]] = None) -> Optional[str]:
    """Capture the screen, saving to ``file_path`` when one is given.

    ``screen_region`` is ``[x1, y1, x2, y2]``, matching the X11 backend's
    calling convention.

    :param file_path: where to write the PNG, or None to discard the capture.
    :param screen_region: region to capture, or None for the whole layout.
    :return: ``file_path`` unchanged, so callers can chain on it.
    """
    image = grab_image(screen_region)
    if file_path:
        try:
            image.save(file_path)
        except (OSError, ValueError) as error:
            raise AutoControlScreenException(
                f"Failed to save screenshot to {file_path!r}: {error}",
            ) from error
    return file_path


def parse_wlr_randr(text: str) -> List[Tuple[int, int, int, int]]:
    """Parse ``wlr-randr`` into ``(x, y, width, height)`` per enabled output.

    An output block starts at a line with no leading whitespace and its
    fields are indented under it::

        HEADLESS-2 "Headless output 1"
          Enabled: yes
          Modes:
            1280x720 px (current)
          Position: 0,0

    Taking the first ``WxH`` in the whole document — which is what this used
    to do — reads one monitor's mode and calls it the screen size. On any
    multi-output layout that disagrees with :func:`grab_image`, which returns
    the whole layout, and the two are composed by the mss-shaped shim.
    """
    rects: List[Tuple[int, int, int, int]] = []
    mode: Optional[Tuple[int, int]] = None
    position: Optional[Tuple[int, int]] = None
    enabled = True

    def flush() -> None:
        if enabled and mode is not None:
            x, y = position if position is not None else (0, 0)
            rects.append((x, y, mode[0], mode[1]))

    for line in text.splitlines():
        if line and not line[0].isspace():
            flush()
            mode, position, enabled = None, None, True
            continue
        enabled_match = _ENABLED_RE.match(line)
        if enabled_match:
            enabled = enabled_match.group(1).lower() == "yes"
            continue
        position_match = _POSITION_RE.match(line)
        if position_match:
            position = (int(position_match.group(1)),
                        int(position_match.group(2)))
            continue
        if "current" in line:
            mode_match = _MODE_RE.search(line)
            if mode_match:
                mode = (int(mode_match.group(1)), int(mode_match.group(2)))
    flush()
    return rects


def _wlr_randr_rects() -> List[Tuple[int, int, int, int]]:
    """Enabled outputs as ``(x, y, width, height)``, empty when unknown.

    Not cached: an output can be plugged in, unplugged or moved between two
    captures, and a stale layout is worse than the ``shutil.which`` miss
    this costs on the desktops that have no ``wlr-randr`` at all.
    """
    executable = binary_path(WAYLAND_WLR_RANDR)
    if executable is None:
        return []
    try:
        output = wayland_capture.run_tool([executable], timeout=5.0).decode(
            "utf-8", errors="replace",
        )
    except AutoControlScreenException:
        return []
    return parse_wlr_randr(output)


def _size_from_wlr_randr() -> Optional[Tuple[int, int]]:
    """Layout bounding box size from ``wlr-randr``, or None when it cannot say."""
    rects = _wlr_randr_rects()
    if not rects:
        return None
    left = min(x for x, _, _, _ in rects)
    top = min(y for _, y, _, _ in rects)
    right = max(x + width for x, _, width, _ in rects)
    bottom = max(y + height for _, y, _, height in rects)
    return (right - left, bottom - top)


__all__ = ["get_pixel", "grab_image", "layout_origin", "parse_wlr_randr",
           "screenshot", "size"]
