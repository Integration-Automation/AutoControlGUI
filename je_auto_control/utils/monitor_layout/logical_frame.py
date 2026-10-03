"""Capture a frame whose pixels map 1:1 onto the coordinates the mouse takes.

On Windows a fresh AutoControl process requests per-monitor v2 before Qt,
so captures and input use physical global coordinates. Primary-only Pillow
captures miss secondary monitors, therefore this module captures the virtual
desktop and reports its possibly negative origin.

An embedding host may already have set its DPI policy; Windows disallows
changing that process policy. The existing rescale fallback remains for
those hosts, whose mixed-DPI mapping is limited by their chosen policy.
On macOS capture each display in global points, resize its Retina pixels
independently, and stitch the displays at their global origins. All APIs
here return one image pixel per input coordinate.

Wayland has the same requirement without the DPI half: its capture spans the
compositor's whole output layout, and that layout starts at a negative
coordinate whenever an output sits left of or above the origin. There is no
``GetSystemMetrics`` to ask, so the origin comes from the backend itself
(``screen_grabber.backend_layout_rect``) — without it a hit found in the frame
is reported 1920 px (or whatever the left-hand monitor is wide) to the right of
where it was matched.

The arithmetic (:func:`needs_rescale`, :func:`logical_scale`) is pure and
unit-testable; the OS reader and the grabber are both injectable. Imports no
``PySide6``.
"""
import sys
from typing import Any, Callable, List, Optional, Sequence, Tuple

Rect = Tuple[int, int, int, int]
MetricsReader = Callable[[int], int]

# GetSystemMetrics indices for the virtual desktop, in logical pixels.
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def _system_metrics(index: int) -> int:
    """Read one ``GetSystemMetrics`` value; 0 off Windows."""
    if not sys.platform.startswith("win"):
        return 0
    import ctypes
    return int(ctypes.windll.user32.GetSystemMetrics(index))


def logical_virtual_rect(metrics: Optional[MetricsReader] = None) -> Optional[Rect]:
    """Virtual desktop as ``(x, y, width, height)`` in mouse coordinates.

    ``None`` where the platform cannot report it, so callers skip the rescale
    rather than guess.
    """
    if metrics is None and sys.platform == 'darwin':
        return _union_rects(_mac_display_rects())
    reader = metrics or _system_metrics
    try:
        rect = (reader(SM_XVIRTUALSCREEN), reader(SM_YVIRTUALSCREEN),
                reader(SM_CXVIRTUALSCREEN), reader(SM_CYVIRTUALSCREEN))
    except (OSError, AttributeError, ValueError):
        return None
    return rect if rect[2] > 0 and rect[3] > 0 else None


def logical_scale(physical: Tuple[int, int],
                  logical: Tuple[int, int]) -> Tuple[float, float]:
    """Physical-to-logical pixel ratio per axis."""
    width = physical[0] / logical[0] if logical[0] else 1.0
    height = physical[1] / logical[1] if logical[1] else 1.0
    return width, height


def needs_rescale(physical: Tuple[int, int], logical: Tuple[int, int]) -> bool:
    """Whether a capture is in a different pixel space from the mouse."""
    return bool(logical[0] and logical[1]) and tuple(physical) != tuple(logical)


def _backend_frame_origin() -> Tuple[int, int]:
    """Where a self-capturing backend's frame starts, ``(0, 0)`` by default.

    ``logical_virtual_rect`` reads ``GetSystemMetrics``, so off Windows it
    has nothing to say — but the Wayland backend captures the compositor's
    whole output layout, and that layout starts at a negative coordinate
    whenever an output sits left of or above the origin. Treating the frame
    as starting at ``(0, 0)`` there offsets every located hit by the origin,
    which reads as "the click lands on the wrong monitor" rather than as a
    failure to find.
    """
    from je_auto_control.utils.cv2_utils.screen_grabber import backend_layout_origin
    return backend_layout_origin()


def _load_image_grab() -> Any:
    """Load the platform's ``ImageGrab``-shaped grabber lazily.

    Pillow off Wayland, the compositor's capture tool on it — see
    :mod:`je_auto_control.utils.cv2_utils.screen_grabber`.
    """
    from je_auto_control.utils.cv2_utils.screen_grabber import image_grabber
    return image_grabber()


def _resample():
    """Pillow's high-quality downscale filter, across Pillow versions."""
    from PIL import Image
    return getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def _mac_display_rects() -> List[Rect]:
    """Active Quartz display bounds in global points, primary first."""
    from je_auto_control.utils.exception.exceptions import AutoControlScreenException
    try:
        import Quartz
    except ImportError as error:
        raise AutoControlScreenException('macOS display geometry requires pyobjc/Quartz') from error
    status, displays, _count = Quartz.CGGetActiveDisplayList(64, None, None)
    if status != 0 or not displays:
        raise AutoControlScreenException(f'CGGetActiveDisplayList failed: {status}')
    main = Quartz.CGMainDisplayID()
    ordered = sorted(displays, key=lambda display: display != main)
    rectangles = []
    for display in ordered:
        bounds = Quartz.CGDisplayBounds(display)
        rectangles.append((round(bounds.origin.x), round(bounds.origin.y),
                           round(bounds.size.width), round(bounds.size.height)))
    return rectangles


def _union_rects(rectangles: Sequence[Rect]) -> Rect:
    left = min(rect[0] for rect in rectangles)
    top = min(rect[1] for rect in rectangles)
    right = max(rect[0] + rect[2] for rect in rectangles)
    bottom = max(rect[1] + rect[3] for rect in rectangles)
    return left, top, right - left, bottom - top


def _mac_region(grabber: Any, region: Sequence[int]) -> Tuple[Any, int, int]:
    """Normalize a global-point bbox independently of its display's Retina ratio.

    Resizing explicitly supports Pillow releases before scale_down was added.
    A native -R capture addresses the region directly, including negative points.
    """
    left, top, width, height = (int(value) for value in region)
    image = grabber.grab(bbox=(left, top, left + width, top + height))
    if needs_rescale(image.size, (width, height)):
        image = image.resize((width, height), _resample())
    return image, left, top


def _grab_mac(grabber: Any, region: Optional[Sequence[int]],
              all_screens: bool) -> Tuple[Any, int, int]:
    if region is not None:
        return _mac_region(grabber, region)
    displays = _mac_display_rects()
    if not all_screens:
        return _mac_region(grabber, displays[0])
    from PIL import Image
    left, top, width, height = _union_rects(displays)
    canvas = Image.new('RGB', (width, height))
    for display in displays:
        image, x, y = _mac_region(grabber, display)
        canvas.paste(image, (x - left, y - top))
    return canvas, left, top


def grab_logical(region: Optional[Sequence[int]] = None, *,
                 all_screens: bool = True,
                 grabber: Optional[Any] = None,
                 metrics: Optional[MetricsReader] = None) -> Tuple[Any, int, int]:
    """Capture the screen in mouse-coordinate space.

    :param region: ``(x, y, width, height)`` in mouse coordinates, or ``None``
        for everything.
    :param all_screens: include monitors beyond the primary one.
    :param grabber: ``ImageGrab``-shaped object, for tests.
    :param metrics: ``GetSystemMetrics``-shaped reader, for tests.
    :return: ``(image, origin_x, origin_y)`` — add the origin to any hit found in
        the image to get a coordinate the mouse can be sent to.
    """
    image_grab = grabber or _load_image_grab()
    if sys.platform == 'darwin':
        return _grab_mac(image_grab, region, all_screens)
    if region is None and not all_screens:
        # The primary-only grab is already in logical pixels and starts at (0, 0).
        return image_grab.grab(), 0, 0

    image = image_grab.grab(all_screens=True)
    rect = logical_virtual_rect(metrics)
    origin_x, origin_y = (rect[0], rect[1]) if rect else _backend_frame_origin()
    if rect and needs_rescale((image.width, image.height), (rect[2], rect[3])):
        image = image.resize((rect[2], rect[3]), _resample())
    if region is None:
        return image, origin_x, origin_y

    # Crop on the rescaled frame, never through ImageGrab's bbox: that crop
    # happens in physical pixels and would cut the wrong place on a scaled screen.
    left, top, width, height = (int(value) for value in region)
    image = image.crop((left - origin_x, top - origin_y,
                        left - origin_x + width, top - origin_y + height))
    return image, left, top
