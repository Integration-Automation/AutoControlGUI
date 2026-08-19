"""One place that decides how this platform's pixels are read.

Pillow's ``ImageGrab`` and ``mss`` both read the X11 root window on Linux.
Under a Wayland session that root belongs to XWayland, which does not
composite native Wayland windows, so what comes back is not the desktop the
user sees.

Pillow does have a fallback — but a narrower one than it first appears.
Reading ``PIL/ImageGrab.py``: the ``gnome-screenshot`` / ``grim`` /
``spectacle`` path runs only inside ``except OSError`` around
``grabscreen_x11``, so it fires when Pillow lacks XCB or there is no X
display at all. With XWayland running — the default on GNOME, KDE and sway —
``DISPLAY`` is set and the X11 grab *succeeds*, so the fallback never
triggers and the caller gets the XWayland root. ``mss`` has no fallback in
any configuration.

Every locator, OCR call, screenshot, recording and remote-desktop frame in
the framework reached for one of those two libraries directly, so on the
common Wayland setup none of them saw the real screen while the Wayland
backend's own capture went unused. Routing through the backend also makes
the behaviour deterministic rather than dependent on whether XWayland
happens to be running, lets ``grim`` apply a region natively, and gives a
failure an actionable message instead of a blank frame.

A platform backend that the generic libraries cannot see through publishes
a ``grab_image(screen_region=None) -> PIL.Image.Image`` function (only
:mod:`je_auto_control.linux_wayland.screen` needs to today). This module
wraps it in whichever library shape the caller already uses, so call sites
stay as they were:

* :func:`image_grabber` — an ``ImageGrab``-shaped object (``.grab(bbox=...)``).
* :func:`mss_grabber` — an ``mss.mss()``-shaped context manager
  (``.monitors``, ``.grab(monitor)``).

A backend may also publish ``layout_origin() -> (x, y)``, the coordinate its
whole-screen capture starts at. It is ``(0, 0)`` for most desktops and
negative on any layout with a monitor left of or above the primary one, which
is why :func:`backend_layout_origin` reports it rather than letting each
caller assume the frame begins at the origin.

Where the backend publishes no ``grab_image`` — Windows, macOS, Linux X11 —
both functions hand back the real library untouched, so nothing about those
platforms changes.
"""
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException

Region = Sequence[int]
GrabImage = Callable[..., Any]


def backend_grab_image() -> Optional[GrabImage]:
    """Return the active platform backend's ``grab_image``, or None.

    None means the generic libraries can see this session and should be
    used as-is.
    """
    try:
        from je_auto_control.wrapper.platform_wrapper import screen
    except (ImportError, AutoControlException):
        return None
    return getattr(screen, "grab_image", None)


class _BackendImageGrab:  # pylint: disable=too-few-public-methods  # reason: must expose exactly ImageGrab's surface
    """``ImageGrab``-shaped adapter over a backend's ``grab_image``."""

    def __init__(self, grab_image: GrabImage) -> None:
        self._grab_image = grab_image

    def grab(self, bbox: Optional[Region] = None, **_kwargs: Any) -> Any:
        """Capture ``bbox`` (left, top, right, bottom), or everything.

        ``ImageGrab``'s other keywords (``all_screens``, ``xdisplay``,
        ``include_layered_windows``) are accepted and ignored: a Wayland
        capture already spans the whole output layout and has no X display
        to name, so honouring them would mean promising a distinction the
        compositor does not offer.
        """
        return self._grab_image(screen_region=list(bbox) if bbox is not None else None)


class _BackendShot:
    """``mss.ScreenShot``-shaped view of one captured image."""

    def __init__(self, image: Any, left: int, top: int) -> None:
        self._image = image if image.mode == "RGB" else image.convert("RGB")
        self.width = int(self._image.width)
        self.height = int(self._image.height)
        self.left = int(left)
        self.top = int(top)
        self.bgra = self._image.convert("RGBA").tobytes("raw", "BGRA")
        # numpy reads this to build an array, the same way mss's own
        # ScreenShot exposes its BGRA buffer.
        self.__array_interface__ = {
            "version": 3,
            "shape": (self.height, self.width, 4),
            "typestr": "|u1",
            "data": self.bgra,
        }

    @property
    def size(self) -> Tuple[int, int]:
        """``(width, height)``, as ``mss.ScreenShot.size`` reports it."""
        return self.width, self.height

    @property
    def pos(self) -> Tuple[int, int]:
        """``(left, top)`` of the captured rectangle."""
        return self.left, self.top

    @property
    def rgb(self) -> bytes:
        """The frame as packed RGB bytes."""
        return self._image.tobytes()


class _BackendMss:
    """``mss.mss()``-shaped adapter over a backend's ``grab_image``.

    The compositor reports one seamless output layout rather than the
    per-monitor rectangles mss enumerates, so ``monitors`` holds the
    combined desktop twice: index 0 by mss's convention, and index 1 so
    callers that default to "the first real screen" still get a frame.
    """

    def __init__(self, grab_image: GrabImage,
                 screen_size: Callable[[], Tuple[int, int]],
                 layout_origin: Optional[Callable[[], Tuple[int, int]]] = None) -> None:
        self._grab_image = grab_image
        self._screen_size = screen_size
        self._layout_origin = layout_origin or (lambda: (0, 0))
        self._monitors: Optional[List[Dict[str, int]]] = None

    @property
    def monitors(self) -> List[Dict[str, int]]:
        """Monitor rectangles, mss-style: index 0 spans the whole desktop.

        ``left`` / ``top`` are the layout's origin rather than a hardcoded
        ``(0, 0)``: mss reports a negative left for a monitor placed to the
        left of the primary one, and :meth:`grab` feeds these straight back
        as a capture region — so a layout with a negative origin described
        as starting at ``(0, 0)`` grabs a rectangle that is off the screen
        on one side and misses that much of the desktop on the other.
        """
        if self._monitors is None:
            width, height = self._screen_size()
            left, top = self._layout_origin()
            layout = {"left": int(left), "top": int(top),
                      "width": int(width), "height": int(height)}
            self._monitors = [dict(layout), dict(layout)]
        return self._monitors

    def grab(self, monitor: Dict[str, int]) -> _BackendShot:
        """Capture one monitor rectangle and return an mss-shaped shot."""
        left = int(monitor["left"])
        top = int(monitor["top"])
        right = left + int(monitor["width"])
        bottom = top + int(monitor["height"])
        image = self._grab_image(screen_region=[left, top, right, bottom])
        return _BackendShot(image, left, top)

    def close(self) -> None:
        """No handle to release; present so the mss shape is complete."""

    def __enter__(self) -> "_BackendMss":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def _backend_screen_size() -> Tuple[int, int]:
    from je_auto_control.wrapper.platform_wrapper import screen
    return screen.size()


def backend_layout_origin() -> Tuple[int, int]:
    """Top-left of the backend's whole-screen capture, in screen coordinates.

    ``(0, 0)`` for a backend that publishes no ``layout_origin`` — which is
    every backend the generic libraries can already see (Windows, macOS,
    X11), and the right answer for any layout that starts at the origin
    anyway. Only the origin is reported, never the size: a caller that has
    the frame already knows how big it is, and asking a backend for its
    size can cost a whole extra capture where no tool can report it.
    """
    try:
        from je_auto_control.wrapper.platform_wrapper import screen
    except (ImportError, AutoControlException):
        return (0, 0)
    origin = getattr(screen, "layout_origin", None)
    if not callable(origin):
        return (0, 0)
    # pylint: disable=not-callable  # reason: pylint resolves the getattr to its
    # None default against whichever backend this host imports, and every
    # backend but Wayland publishes no layout_origin; callable() is the check.
    left, top = origin()
    return (int(left), int(top))


def image_grabber() -> Any:
    """Return an ``ImageGrab``-shaped grabber for the current platform."""
    grab_image = backend_grab_image()
    if grab_image is None:
        from PIL import ImageGrab
        return ImageGrab
    return _BackendImageGrab(grab_image)


def mss_grabber() -> Any:
    """Return an ``mss.mss()``-shaped grabber for the current platform.

    Use in place of ``mss.mss()``; the result is a context manager either
    way, so ``with mss_grabber() as sct:`` works unchanged.
    """
    grab_image = backend_grab_image()
    if grab_image is None:
        import mss
        # mss 10 deprecated the lowercase factory in favour of MSS; both
        # yield the same platform class, so prefer the one that is current.
        return (getattr(mss, "MSS", None) or mss.mss)()
    return _BackendMss(grab_image, _backend_screen_size,
                       backend_layout_origin)


__all__ = ["backend_grab_image", "backend_layout_origin", "image_grabber",
           "mss_grabber"]
