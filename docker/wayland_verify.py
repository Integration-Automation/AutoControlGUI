"""Verify AutoControl's Wayland backend against a real wlroots compositor.

Runs inside a headless sway session (see ``Dockerfile.wayland``). Everything
the unit tests can only assert against a mock is checked here against the
compositor itself: the argv grim actually accepts, the geometry string it
actually honours, the output format wlr-randr actually prints, and whether
the whole ``screenshot()`` -> ``screen_grabber`` -> ``capture`` ->
``grab_image`` chain really returns the pixels on screen.

Ground truth comes from ``swaymsg -t get_outputs`` — the compositor's own
report — rather than from an assumption about how sway lays two headless
outputs out. That matters: sway puts HEADLESS-2 at x=0 and HEADLESS-1 to its
right, so anything keyed on list order rather than on the reported geometry
tests the wrong pixel. The two outputs are painted different solid colours so
a region grab has something to get *wrong*: on a uniform screen any rectangle
looks correct.

The entrypoint runs this twice, against two sway configs. The second one
moves HEADLESS-1 to ``position -1280 0``, which is the layout a desktop has
whenever a monitor sits left of (or above) the primary one: the capture then
starts at a negative coordinate, and everything that maps a pixel to a screen
coordinate has to subtract that origin rather than assume ``(0, 0)``. Nothing
below is written for one layout or the other — every coordinate is derived
from what the compositor reports.

Exit status is the number of failed checks, so the container's exit code
says whether this passed.
"""
from __future__ import annotations

import json
import os
import subprocess  # nosec B404  # reason: argv-list, fixed tool names, no shell
import sys
import tempfile
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

# Painted onto the named outputs by the sway config. Deliberately asymmetric
# in every channel so a red/blue swap cannot pass. Which one ends up on the
# left is sway's business, so everything below keys on the *name*.
OUTPUT_COLOURS = {
    "HEADLESS-1": (0x12, 0x34, 0x56),
    "HEADLESS-2": (0xAB, 0xCD, 0xEF),
}

_results: List[Tuple[str, bool, str]] = []


@dataclass(frozen=True)
class Layout:
    """The compositor's output layout, as this run found it."""

    origin_x: int
    origin_y: int
    width: int
    height: int
    outputs: List[dict]

    @property
    def left(self) -> dict:
        """The left-most output."""
        return self.outputs[0]

    @property
    def right(self) -> dict:
        """The right-most output (the left-most one when there is only one)."""
        return self.outputs[-1]

    @property
    def multi(self) -> bool:
        """Whether there is more than one output to tell apart."""
        return len(self.outputs) > 1

    def colour(self, output: dict) -> Tuple[int, int, int]:
        """The solid colour sway was told to paint ``output``."""
        return OUTPUT_COLOURS[output["name"]]

    def image_point(self, x: int, y: int) -> Tuple[int, int]:
        """Layout coordinate ``(x, y)`` as a pixel index into a full capture."""
        return (x - self.origin_x, y - self.origin_y)

    def inside(self, output: dict, dx: int = 10, dy: int = 10) -> Tuple[int, int]:
        """A layout coordinate ``(dx, dy)`` into ``output``."""
        rect = output["rect"]
        return (rect["x"] + dx, rect["y"] + dy)


def check(name: str, fn: Callable[[], Any]) -> Any:
    """Run one check, record pass/fail, and keep going either way."""
    try:
        detail = fn()
    except Exception:  # noqa: BLE001  # reason: a failed check must not stop the rest
        _results.append((name, False, traceback.format_exc(limit=3).strip()))
        print(f"FAIL  {name}")
        print("        " + traceback.format_exc(limit=3).strip().replace(
            "\n", "\n        "))
        return None
    _results.append((name, True, str(detail)))
    print(f"ok    {name}" + (f"  — {detail}" if detail else ""))
    return detail


def note(message: str) -> None:
    print(f"      {message}")


def sway_outputs() -> List[dict]:
    """The compositor's own description of its outputs."""
    raw = subprocess.run(  # nosec B603 B607  # nosemgrep
        ["swaymsg", "-t", "get_outputs", "-r"],
        check=True, stdout=subprocess.PIPE).stdout
    return json.loads(raw)


def read_layout() -> Layout:
    """Describe the live layout, sorted so "left" and "right" mean what they say."""
    outputs = sorted(sway_outputs(), key=lambda o: o["rect"]["x"])
    origin_x = min(o["rect"]["x"] for o in outputs)
    origin_y = min(o["rect"]["y"] for o in outputs)
    width = max(o["rect"]["x"] + o["rect"]["width"] for o in outputs) - origin_x
    height = max(o["rect"]["y"] + o["rect"]["height"] for o in outputs) - origin_y
    return Layout(origin_x, origin_y, width, height, outputs)


def report_environment(layout: Layout) -> None:
    """Print what session this is and what the compositor says it is showing."""
    print(f"WAYLAND_DISPLAY  = {os.environ.get('WAYLAND_DISPLAY')!r}")
    print(f"XDG_SESSION_TYPE = {os.environ.get('XDG_SESSION_TYPE')!r}")
    print(f"DISPLAY          = {os.environ.get('DISPLAY')!r}  "
          f"(absent means no XWayland, so nothing can silently fall back to it)")
    for out in layout.outputs:
        rect = out["rect"]
        print(f"output {out['name']}: {rect['width']}x{rect['height']} "
              f"at ({rect['x']},{rect['y']})  "
              f"painted {OUTPUT_COLOURS.get(out['name'])}")
    print(f"layout = {layout.width}x{layout.height} at "
          f"({layout.origin_x},{layout.origin_y})")
    print("-" * 72)


def check_detection(modules: Dict[str, Any]) -> None:
    """The session is seen as Wayland and the capture tier resolves to grim."""
    detect = modules["detect"]
    capture = modules["capture"]
    screen_grabber = modules["screen_grabber"]
    check("session detected as wayland",
          lambda: _assert_eq(detect.select_display_server(), "wayland"))
    check("capture tier resolves to grim",
          lambda: _assert_eq(capture.available_tool(), "grim"))
    check("platform wrapper publishes grab_image",
          lambda: _assert_true(screen_grabber.backend_grab_image() is not None,
                               "backend_grab_image() returned None, so every "
                               "capture would have gone to Pillow/mss"))


def check_geometry(screen: Any, layout: Layout) -> None:
    """wlr-randr's format, the reported size and the origin it implies."""
    def _wlr_randr_raw():
        raw = subprocess.run(  # nosec B603 B607  # nosemgrep
            ["wlr-randr"], check=True,
            stdout=subprocess.PIPE).stdout.decode()
        print("      wlr-randr prints:")
        for line in raw.splitlines()[:8]:
            print(f"        | {line}")
        return "captured"
    check("wlr-randr runs", _wlr_randr_raw)
    check("screen.size() reports the whole layout, not one output",
          lambda: _assert_eq(screen.size(), (layout.width, layout.height)))
    # On the shifted layout these two differ by 1280: the size is the width
    # of the bounding box, never the coordinate of its right edge.
    check("layout_origin() matches what the compositor reports",
          lambda: _assert_eq(screen.layout_origin(),
                             (layout.origin_x, layout.origin_y)))
    full = check("grab_image() full frame",
                 lambda: _size_of(screen.grab_image()))
    check("full frame matches the layout bounding box",
          lambda: _assert_eq(full, (layout.width, layout.height)))


def check_pixels(screen: Any, layout: Layout) -> None:
    """Colour fidelity, grim's -g geometry and get_pixel, in layout coordinates."""
    image = screen.grab_image()
    left_rgb = layout.colour(layout.left)
    right_rgb = layout.colour(layout.right)
    check(f"left output {layout.left['name']} reads its own colour (RGB order)",
          lambda: _assert_eq(image.getpixel(
              layout.image_point(*layout.inside(layout.left))), left_rgb))
    if layout.multi:
        check(f"right output {layout.right['name']} reads its own colour "
              f"(proves the x offset is real)",
              lambda: _assert_eq(image.getpixel(
                  layout.image_point(*layout.inside(layout.right))), right_rgb))

        rx, ry = layout.inside(layout.right, 5, 5)
        region = [rx, ry, rx + 100, ry + 50]
        cropped = check("grab_image(region) honours grim -g size",
                        lambda: _size_of(screen.grab_image(region)))
        check("region is 100x50 as asked", lambda: _assert_eq(cropped, (100, 50)))
        check("region landed on the right-hand output, not at the origin",
              lambda: _assert_eq(screen.grab_image(region).getpixel((0, 0)),
                                 right_rgb))
        lx, ly = layout.inside(layout.left, 5, 5)
        check("a region on the left-hand output reads the left colour",
              lambda: _assert_eq(
                  screen.grab_image([lx, ly, lx + 100, ly + 50]).getpixel((0, 0)),
                  left_rgb))

    check("get_pixel() on the left-hand output",
          lambda: _assert_eq(screen.get_pixel(*layout.inside(layout.left)),
                             left_rgb))
    if layout.multi:
        check("get_pixel() on the right-hand output",
              lambda: _assert_eq(screen.get_pixel(*layout.inside(layout.right)),
                                 right_rgb))


def check_public_paths(modules: Dict[str, Any], layout: Layout) -> None:
    """The chain every locator, recorder and remote-desktop frame goes through."""
    screen = modules["screen"]
    screen_grabber = modules["screen_grabber"]
    left_rgb = layout.colour(layout.left)
    left_point = layout.image_point(*layout.inside(layout.left))

    def _screenshot_file():
        from PIL import Image
        path = os.path.join(
            os.environ.get("XDG_RUNTIME_DIR")
            or tempfile.mkdtemp(prefix="autocontrol-wayland-verify-"),
            "shot.png")
        returned = screen.screenshot(path)
        _assert_eq(returned, path)
        with Image.open(path) as saved:
            return f"{saved.width}x{saved.height} {saved.format}"
    check("screen.screenshot() writes a real PNG", _screenshot_file)

    def _public_screenshot():
        import je_auto_control as ac
        frame = ac.screenshot()
        _assert_eq(frame.shape, (layout.height, layout.width, 3))
        # The wrapper converts to BGR for OpenCV, so the channels reverse.
        pixel = tuple(int(v) for v in frame[left_point[1]][left_point[0]])
        _assert_eq(pixel, tuple(reversed(left_rgb)))
        return f"shape={frame.shape} BGR pixel={pixel}"
    check("je_auto_control.screenshot() returns the real screen in BGR",
          _public_screenshot)

    def _pil_screenshot():
        from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
        return _size_of(pil_screenshot())
    check("pil_screenshot() goes through the backend", _pil_screenshot)

    def _grab_logical():
        from je_auto_control.utils.monitor_layout.logical_frame import grab_logical
        frame, ox, oy = grab_logical()
        _assert_eq(frame.getpixel(left_point), left_rgb)
        # The origin is what a caller adds to a hit found in the frame, so on
        # the shifted layout it has to be the negative one — a locator that
        # gets (0, 0) here clicks 1280 px to the right of what it matched.
        _assert_eq((ox, oy), (layout.origin_x, layout.origin_y))
        return f"{frame.width}x{frame.height} origin=({ox},{oy})"
    check("grab_logical() — the locator and OCR capture path", _grab_logical)

    def _mss_shim():
        with screen_grabber.mss_grabber() as sct:
            monitors = sct.monitors
            _assert_eq((monitors[1]["left"], monitors[1]["top"]),
                       (layout.origin_x, layout.origin_y))
            shot = sct.grab(monitors[1])
        _assert_eq(shot.size, (layout.width, layout.height))
        # mss consumers read .bgra; four bytes per pixel, blue first.
        offset = 4 * (left_point[1] * layout.width + left_point[0])
        _assert_eq(tuple(shot.bgra[offset:offset + 3]), tuple(reversed(left_rgb)))
        return f"{len(monitors)} monitors, monitor[1] at {monitors[1]['left']},{monitors[1]['top']}"
    check("mss-shaped shim (recorder / WebRTC / MCP path)", _mss_shim)


def check_fallback_crop(modules: Dict[str, Any], layout: Layout) -> None:
    """The tiers that cannot apply a region themselves, cropped by us.

    grim is the only helper that takes a geometry; gnome-screenshot,
    spectacle, the portal and an operator's own command all return the whole
    layout and :func:`screen.grab_image` crops afterwards. Pointing the
    operator override at grim is what puts a *real* whole-layout PNG through
    that crop — and on the shifted layout a crop that forgets the origin
    silently returns black padding instead of the left-hand monitor.
    """
    capture = modules["capture"]
    screen = modules["screen"]
    if not layout.multi:
        return
    os.environ[capture.CAPTURE_COMMAND_ENV] = "grim {output}"
    try:
        check("operator override tier is selected",
              lambda: _assert_eq(capture.available_tool(),
                                 f"${capture.CAPTURE_COMMAND_ENV}"))
        check("override returns the whole layout, region unapplied",
              lambda: _assert_eq(
                  (lambda c: (_size_of_png(c.data), c.region_applied))(
                      capture.grab_png([0, 0, 10, 10])),
                  ((layout.width, layout.height), False)))
        for output in (layout.left, layout.right):
            x, y = layout.inside(output, 5, 5)
            check(f"cropped region on {output['name']} reads its own colour",
                  lambda x=x, y=y, output=output: _assert_eq(
                      screen.grab_image([x, y, x + 100, y + 50]).getpixel((0, 0)),
                      layout.colour(output)))
        check("get_pixel() through the cropping tier",
              lambda: _assert_eq(screen.get_pixel(*layout.inside(layout.left)),
                                 layout.colour(layout.left)))
    finally:
        del os.environ[capture.CAPTURE_COMMAND_ENV]


def main() -> int:
    print("=" * 72)
    print("AutoControl Wayland verification — real sway session")
    print("=" * 72)

    layout = read_layout()
    report_environment(layout)

    from je_auto_control.linux_wayland import _detect, capture, screen
    from je_auto_control.linux_wayland import keyboard as wl_keyboard
    from je_auto_control.utils.cv2_utils import screen_grabber
    modules = {"detect": _detect, "capture": capture, "screen": screen,
               "screen_grabber": screen_grabber}

    check_detection(modules)
    check_geometry(screen, layout)
    check_pixels(screen, layout)
    check_public_paths(modules, layout)
    check_fallback_crop(modules, layout)

    def _wtype():
        # Nothing is focused, so the keystrokes go nowhere. What is being
        # checked is that wtype accepts this argv and exits cleanly — the
        # part the unit tests could only assert against a mock.
        wl_keyboard.write("autocontrol")
        return "wtype accepted `wtype -- TEXT`"
    check("wtype argv is accepted by the real binary", _wtype)

    # --- what this environment cannot answer -----------------------------
    print("-" * 72)
    print("NOT verifiable in this container, and why:")
    note("ydotool — needs /dev/uinput, and sway's headless backend consumes")
    note("  no libinput devices, so an injected event has nowhere to land.")
    note("libei / RemoteDesktop portal — xdg-desktop-portal-wlr implements")
    note("  ScreenCast and Screenshot but not RemoteDesktop, so there is no")
    note("  ConnectToEIS here. Covered instead by docker/eis_verify.py (the")
    note("  protocol) and docker/portal_verify.py (the D-Bus handshake).")

    # --- summary ---------------------------------------------------------
    failed = [name for name, ok, _ in _results if not ok]
    print("=" * 72)
    print(f"{len(_results) - len(failed)}/{len(_results)} checks passed")
    for name in failed:
        print(f"  FAILED: {name}")
    print("=" * 72)
    return len(failed)


def _assert_eq(actual: Any, expected: Any) -> str:
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")
    return repr(actual)


def _assert_true(value: bool, message: str) -> str:
    if not value:
        raise AssertionError(message)
    return "yes"


def _size_of(image: Any) -> Tuple[int, int]:
    return (image.width, image.height)


def _size_of_png(data: bytes) -> Tuple[int, int]:
    from io import BytesIO

    from PIL import Image
    with Image.open(BytesIO(data)) as image:
        return (image.width, image.height)


if __name__ == "__main__":
    sys.exit(main())
