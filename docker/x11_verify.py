"""Verify AutoControl's X11 backend against a real X server and real clients.

Runs inside the session ``entrypoint-x11.sh`` brings up (see
``Dockerfile.x11``). Every X11 assertion in the unit suite is made against a
mock of ``python-Xlib``, so none of it could answer the questions that matter:
does an injected event actually reach a client, does it arrive as *real* input
rather than a sent event most applications ignore, and is a captured pixel the
pixel that is on screen.

Ground truth deliberately comes from outside the code under test:

* ``xev`` is a real X client. Its window prints every event delivered to it,
  so an XTest-injected click is read back the way the ydotool job reads its
  events back off ``/dev/input/eventN`` — including ``synthetic NO``, which is
  what separates server-level input from ``XSendEvent`` traffic that toolkits
  routinely discard.
* ``import`` (ImageMagick) is an independent grabber, in the role ``grim``
  plays for Wayland. The root window is painted two asymmetric colours first,
  because on a uniform screen any wrong rectangle looks right.
* ``xdotool`` and ``xdpyinfo`` are the server answering for itself about
  pointer position and geometry.

The entrypoint runs this twice: once with a single monitor covering the
screen, once with two RANDR monitors side by side. Nothing below is written
for one layout or the other — every coordinate is derived from what the
server reports.

There is deliberately no negative-origin pass. On X11 the root window is the
union of every monitor and always starts at ``(0, 0)``, so a monitor placed to
the left shifts the others right rather than moving the origin. The Wayland
job's second layout has no analogue here; that is a protocol difference, not
an untested case.

Exit status is the number of failed checks, so the container's exit code says
whether this passed.
"""
from __future__ import annotations

import os
import re
import subprocess  # nosec B404  # reason: argv lists of fixed tool names, no shell
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

#: Painted onto the two halves of the root window. Asymmetric in every
#: channel so a red/blue swap cannot pass, and different from each other so a
#: region grab has something to get wrong.
LEFT_COLOUR = (0x12, 0x34, 0x56)
RIGHT_COLOUR = (0xAB, 0xCD, 0xEF)

#: How long an injected event is given to come back out of a real client.
EVENT_TIMEOUT = 5.0

#: Everything this run writes goes here, as the sibling verification
#: scripts do, rather than into shared /tmp paths another process could
#: already own.
SCRATCH = tempfile.mkdtemp(prefix="autocontrol-x11-verify-")

_results: List[Tuple[str, bool, str]] = []


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
    """Print an indented remark that is not a check."""
    print(f"      {message}")


def _run(argv: List[str], *, timeout: float = 15.0) -> str:
    """Run one tool from this image and return its stdout."""
    # argv is assembled from literals in this file; no shell, no user input.
    completed = subprocess.run(argv, check=True,  # nosec B603 B607  # nosemgrep
                               timeout=timeout,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    return completed.stdout.decode("utf-8", errors="replace")


def _assert_eq(actual: Any, expected: Any) -> str:
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")
    return repr(actual)


def _assert_true(value: bool, message: str) -> str:
    if not value:
        raise AssertionError(message)
    return "yes"


# --- the server's own description of itself --------------------------------


@dataclass(frozen=True)
class Monitor:
    """One RANDR monitor, as ``xrandr --listmonitors`` reports it."""

    name: str
    x: int
    y: int
    width: int
    height: int

    def inside(self, dx: int = 40, dy: int = 40) -> Tuple[int, int]:
        """A screen coordinate ``(dx, dy)`` into this monitor."""
        return (self.x + dx, self.y + dy)


@dataclass(frozen=True)
class Layout:
    """The screen and the monitors carved out of it."""

    width: int
    height: int
    monitors: List[Monitor]

    @property
    def multi(self) -> bool:
        """Whether there is more than one monitor to tell apart."""
        return len(self.monitors) > 1


_MONITOR_RE = re.compile(
    r"^\s*\d+:\s+\+?\*?(?P<name>\S+)\s+"
    r"(?P<w>\d+)/\d+x(?P<h>\d+)/\d+\+(?P<x>\d+)\+(?P<y>\d+)",
)


def read_layout() -> Layout:
    """Describe the live screen from the server's own answers."""
    dimensions = re.search(r"dimensions:\s+(\d+)x(\d+)", _run(["xdpyinfo"]))
    if dimensions is None:
        raise RuntimeError("xdpyinfo reported no dimensions")
    width, height = int(dimensions.group(1)), int(dimensions.group(2))

    monitors: List[Monitor] = []
    for line in _run(["xrandr", "--listmonitors"]).splitlines():
        found = _MONITOR_RE.match(line)
        if found is None:
            continue
        monitors.append(Monitor(
            name=found.group("name"),
            x=int(found.group("x")), y=int(found.group("y")),
            width=int(found.group("w")), height=int(found.group("h")),
        ))
    if not monitors:
        # A screen with no RANDR monitor is still a screen; treat the whole
        # root window as one rather than inventing geometry.
        monitors.append(Monitor("screen", 0, 0, width, height))
    monitors.sort(key=lambda monitor: monitor.x)
    return Layout(width=width, height=height, monitors=monitors)


def paint_root(layout: Layout) -> None:
    """Paint the root window's two halves in the known colours.

    Uses python-Xlib directly. Painting is setup, not subject: what is under
    test is whether the *readers* agree with each other and with an
    independent grabber about what ended up there.
    """
    from Xlib import display as xdisplay

    connection = xdisplay.Display()
    screen = connection.screen()
    root = screen.root
    pixmap = root.create_pixmap(layout.width, layout.height, screen.root_depth)
    context = pixmap.create_gc()
    half = layout.width // 2
    for colour, left, span in (
            (LEFT_COLOUR, 0, half),
            (RIGHT_COLOUR, half, layout.width - half),
    ):
        context.change(foreground=(colour[0] << 16) | (colour[1] << 8) | colour[2])
        pixmap.fill_rectangle(context, left, 0, span, layout.height)
    root.change_attributes(background_pixmap=pixmap)
    root.clear_area(x=0, y=0, width=layout.width, height=layout.height)
    connection.sync()
    # The pixmap must outlive this function: the server keeps a reference for
    # the background, but freeing the client-side resource here would take it
    # with us. Parking it on the module keeps the background painted.
    globals()["_ROOT_PIXMAP"] = (connection, pixmap)


def expected_colour(layout: Layout, x: int) -> Tuple[int, int, int]:
    """The colour :func:`paint_root` put at screen column ``x``."""
    return LEFT_COLOUR if x < layout.width // 2 else RIGHT_COLOUR


def truth_capture(path: Optional[str] = None):
    """Grab the root window with ImageMagick and return it as a Pillow image."""
    from PIL import Image

    path = path or os.path.join(SCRATCH, "truth.png")
    _run(["import", "-window", "root", "-silent", path])
    with Image.open(path) as opened:
        return opened.convert("RGB").copy()


# --- a real client that reports what reached it ----------------------------


_EVENT_HEAD_RE = re.compile(r"^(\w+) event,")
_BUTTON_RE = re.compile(r"\bbutton (\d+)\b")
_KEYCODE_RE = re.compile(r"\bkeycode (\d+)\b")
_KEYSYM_RE = re.compile(r"\(keysym 0x[0-9a-f]+, (\S+)\)")
_ROOT_XY_RE = re.compile(r"\broot:\((-?\d+),(-?\d+)\)")
_SYNTHETIC_RE = re.compile(r"\bsynthetic (\w+)\b")


class EventTester:
    """``xev``: a real X client whose window prints what is delivered to it.

    An event injected through XTest travels through the server and is
    dispatched like any other, so what this reads back is the arrival, not the
    call. ``xev`` is line-buffered through ``stdbuf`` because its output is a
    pipe here rather than a terminal, and a block-buffered log would report
    nothing until it filled.
    """

    LOG_PATH = os.path.join(SCRATCH, "xev.log")
    WINDOW_NAME = "Event Tester"

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._handle = None
        self._offset = 0
        # Text read but not yet forming a whole record. xev is writing while
        # this reads, so the tail of any read is routinely half an event:
        # parsing it would report a KeyPress whose keycode had not been
        # written yet, which looks exactly like a backend that sent no keycode.
        self._pending = ""
        # Consecutive reads that returned nothing. xev separates records with
        # a blank line but writes no terminator after the last one, so the
        # most recent event stays unterminated until the *next* one arrives —
        # and a press with nothing after it would never be reported at all.
        # Two silent reads is what says the record is finished rather than
        # half-written.
        self._idle_reads = 0
        # Parsed events not yet consumed by a check. Draining must not
        # discard what the caller did not ask for — a click writes press and
        # release into one chunk, and a reader that returns the press and
        # drops the release makes a working click look like a stuck button.
        self._events: List[Dict[str, Any]] = []
        self.window_id = 0
        self.rect: Tuple[int, int, int, int] = (0, 0, 0, 0)

    def __enter__(self) -> "EventTester":
        self._handle = open(self.LOG_PATH, "wb")  # noqa: SIM115  # reason: closed in __exit__
        # stdbuf + xev, both from this image; no shell, no user input.
        self._process = subprocess.Popen(  # nosec B603 B607  # nosemgrep
            ["stdbuf", "-oL", "xev", "-geometry", "400x300+80+80"],
            stdout=self._handle, stderr=subprocess.STDOUT)
        self.window_id = self._await_window()
        self.rect = self._read_geometry()
        # The window manager decides where the window lands and what has
        # focus, so ask for focus rather than assume the map gave it.
        _run(["xdotool", "windowactivate", "--sync", str(self.window_id)])
        _run(["xdotool", "windowfocus", "--sync", str(self.window_id)])
        self.flush()
        return self

    def __exit__(self, *_exception: Any) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        if self._handle is not None:
            self._handle.close()

    def _await_window(self) -> int:
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            try:
                found = _run(["xdotool", "search", "--name", self.WINDOW_NAME])
            except subprocess.CalledProcessError:
                found = ""
            ids = [line for line in found.split() if line.isdigit()]
            if ids:
                return int(ids[-1])
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError(
                    f"xev exited {self._process.returncode} before mapping a window")
            time.sleep(0.1)
        raise RuntimeError("xev never mapped a window")

    def _read_geometry(self) -> Tuple[int, int, int, int]:
        shell = _run(["xdotool", "getwindowgeometry", "--shell",
                      str(self.window_id)])
        values: Dict[str, int] = {}
        for line in shell.splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                if value.strip().lstrip("-").isdigit():
                    values[key.strip()] = int(value)
        return (values.get("X", 0), values.get("Y", 0),
                values.get("WIDTH", 0), values.get("HEIGHT", 0))

    def centre(self) -> Tuple[int, int]:
        """The screen coordinate at the middle of the tester's window."""
        x, y, width, height = self.rect
        return (x + width // 2, y + height // 2)

    def drain(self) -> List[Dict[str, Any]]:
        """Buffer every *complete* record written since the last read."""
        with open(self.LOG_PATH, "rb") as log:
            log.seek(self._offset)
            raw = log.read()
        self._offset += len(raw)
        self._idle_reads = 0 if raw else self._idle_reads + 1
        self._pending += raw.decode("utf-8", errors="replace")
        # xev separates records with a blank line, so everything after the
        # last one may still be being written. Keep it for the next read.
        chunks = re.split(r"\n\s*\n", self._pending)
        self._pending = chunks.pop()
        # ...unless nothing has been written for two reads running and what is
        # held ends in a newline. Then it is not half-written, it is the last
        # record, and holding it would lose every event that happens to be
        # final — which is every press that is waiting for its release.
        if (self._idle_reads >= 2 and self._pending.endswith("\n")
                and _EVENT_HEAD_RE.match(self._pending.strip())):
            chunks.append(self._pending)
            self._pending = ""
        fresh: List[Dict[str, Any]] = []
        for record in chunks:
            head = _EVENT_HEAD_RE.match(record.strip())
            if head is None:
                continue
            fresh.append(_parse_record(head.group(1), record))
        self._events.extend(fresh)
        return fresh

    def flush(self) -> None:
        """Forget everything so far, so a check starts from a clean slate."""
        self.drain()
        self._events.clear()

    def buffered(self, kind: str, settle: float = 0.5) -> List[Dict[str, Any]]:
        """Events of ``kind`` that have arrived and nothing has claimed.

        Used to assert an *absence*, so it drains until the reader has gone
        quiet: returning early would report "nothing arrived" for an event
        still sitting unterminated in the buffer.
        """
        deadline = time.monotonic() + settle
        while time.monotonic() < deadline:
            self.drain()
            time.sleep(0.05)
        return [event for event in self._events if event["type"] == kind]

    def collect(self, kind: str, count: int = 1,
                timeout: float = EVENT_TIMEOUT) -> List[Dict[str, Any]]:
        """Wait for ``count`` events of ``kind``, or raise saying what came.

        What is taken is removed from the buffer and what is not stays there,
        so consecutive collects for different kinds see the same arrival.
        """
        deadline = time.monotonic() + timeout
        while True:
            self.drain()
            wanted = [event for event in self._events if event["type"] == kind]
            if len(wanted) >= count:
                taken = wanted[:count]
                for event in taken:
                    self._events.remove(event)
                return taken
            if time.monotonic() >= deadline:
                raise AssertionError(
                    f"waited {timeout}s for {count}x {kind}; the buffer holds "
                    f"{[event['type'] for event in self._events]}")
            time.sleep(0.05)


def _parse_record(kind: str, record: str) -> Dict[str, Any]:
    """Turn one xev record into the fields the checks care about."""
    button = _BUTTON_RE.search(record)
    keycode = _KEYCODE_RE.search(record)
    keysym = _KEYSYM_RE.search(record)
    root_xy = _ROOT_XY_RE.search(record)
    synthetic = _SYNTHETIC_RE.search(record)
    return {
        "type": kind,
        "button": int(button.group(1)) if button else None,
        "keycode": int(keycode.group(1)) if keycode else None,
        "keysym": keysym.group(1) if keysym else None,
        "root": ((int(root_xy.group(1)), int(root_xy.group(2)))
                 if root_xy else None),
        "synthetic": synthetic.group(1) if synthetic else None,
    }


# --- checks ----------------------------------------------------------------


def report_environment(layout: Layout) -> None:
    """Print what this run is actually working against."""
    print("-" * 72)
    note(f"DISPLAY={os.environ.get('DISPLAY')!r} "
         f"XDG_SESSION_TYPE={os.environ.get('XDG_SESSION_TYPE')!r}")
    note(f"screen: {layout.width}x{layout.height}")
    for monitor in layout.monitors:
        note(f"monitor {monitor.name}: {monitor.width}x{monitor.height} "
             f"at ({monitor.x}, {monitor.y})")
    print("-" * 72)


def check_backend_selection() -> None:
    """The wrapper must land on the X11 backend, not fall through to Wayland."""
    def _selected() -> str:
        from je_auto_control.wrapper import platform_wrapper

        module = platform_wrapper.mouse.__name__
        _assert_true("linux_with_x11" in module,
                     f"expected the X11 backend, got {module}")
        return module
    check("the platform wrapper selects the X11 backend", _selected)


def check_geometry(layout: Layout) -> None:
    """``screen_size()`` must be the screen the server reports."""
    def _size() -> str:
        from je_auto_control import screen_size

        return _assert_eq(tuple(screen_size()), (layout.width, layout.height))
    check("screen_size() equals the server's dimensions", _size)


def check_pixels(layout: Layout) -> None:
    """Every reader must agree with an independent grabber and each other."""
    from je_auto_control import get_pixel, screenshot

    truth = truth_capture()
    left = layout.monitors[0].inside()
    right = layout.monitors[-1].inside() if layout.multi else (
        layout.width - 40, 40)

    def _truth_is_painted() -> str:
        for point in (left, right):
            _assert_eq(truth.getpixel(point), expected_colour(layout, point[0]))
        return f"{left} and {right} carry the painted colours"
    check("an independent grabber sees the painted colours", _truth_is_painted)

    def _get_pixel() -> str:
        for point in (left, right):
            _assert_eq(tuple(get_pixel(*point)), expected_colour(layout, point[0]))
        return f"get_pixel agrees at {left} and {right}"
    check("get_pixel() returns the colour that is on screen", _get_pixel)

    def _full_screenshot() -> str:
        frame = screenshot()
        _assert_eq((frame.shape[1], frame.shape[0]), (layout.width, layout.height))
        for point in (left, right):
            blue, green, red = frame[point[1], point[0]]
            _assert_eq((int(red), int(green), int(blue)),
                       expected_colour(layout, point[0]))
        return f"{frame.shape[1]}x{frame.shape[0]}, BGR order confirmed"
    check("screenshot() is the whole screen, in BGR", _full_screenshot)

    def _region_screenshot() -> str:
        # A rectangle wholly inside the right-hand colour: if the region were
        # ignored, or applied from the wrong origin, this would pick up the
        # left-hand colour instead of failing silently on a uniform screen.
        x1, y1 = right
        x2, y2 = x1 + 60, y1 + 40
        frame = screenshot(screen_region=[x1, y1, x2, y2])
        _assert_eq((frame.shape[1], frame.shape[0]), (x2 - x1, y2 - y1))
        blue, green, red = frame[2, 2]
        _assert_eq((int(red), int(green), int(blue)), expected_colour(layout, x1))
        return f"region [{x1},{y1},{x2},{y2}] cropped and coloured correctly"
    check("screenshot(screen_region=...) crops from the right origin",
          _region_screenshot)


def check_pointer(layout: Layout) -> None:
    """Where the pointer is put must be where the server says it is."""
    from je_auto_control import get_mouse_position, set_mouse_position

    def _pointer_at(point: Tuple[int, int]) -> str:
        set_mouse_position(*point)
        shell = _run(["xdotool", "getmouselocation", "--shell"])
        values = dict(
            line.split("=", 1) for line in shell.splitlines() if "=" in line)
        server = (int(values["X"]), int(values["Y"]))
        _assert_eq(server, point)
        _assert_eq(tuple(get_mouse_position()), point)
        return f"{point} read back from the server and from get_mouse_position"

    first = layout.monitors[0].inside(120, 120)
    check("set_mouse_position lands where the server says",
          lambda: _pointer_at(first))

    if layout.multi:
        second = layout.monitors[-1].inside(120, 120)
        check("a point on the second monitor lands on the second monitor",
              lambda: _pointer_at(second))
    else:
        note("one monitor in this layout, so there is no second one to reach; "
             "the two-monitor pass covers that.")


def check_button_events(tester: EventTester) -> None:
    """A click must arrive at a real client, as real input, where aimed."""
    from je_auto_control import click_mouse, press_mouse, release_mouse, set_mouse_position

    target = tester.centre()

    def _click() -> str:
        set_mouse_position(*target)
        tester.flush()
        click_mouse("mouse_left")
        press = tester.collect("ButtonPress")[0]
        release = tester.collect("ButtonRelease")[0]
        _assert_eq(press["button"], 1)
        _assert_eq(release["button"], 1)
        _assert_eq(press["root"], target)
        return f"button 1 press+release at {target}"
    check("click_mouse reaches a real client at the aimed point", _click)

    def _not_synthetic() -> str:
        set_mouse_position(*target)
        tester.flush()
        click_mouse("mouse_left")
        press = tester.collect("ButtonPress")[0]
        # XSendEvent traffic arrives with synthetic YES and is discarded by
        # most toolkits. XTest goes through the server, so anything that
        # started reporting YES here would mean the backend had quietly
        # stopped driving real input.
        return _assert_eq(press["synthetic"], "NO")
    check("injected input is real server input, not a sent event",
          _not_synthetic)

    def _split() -> str:
        set_mouse_position(*target)
        tester.flush()
        press_mouse("mouse_right")
        press = tester.collect("ButtonPress")[0]
        _assert_eq(press["button"], 3)
        _assert_true(not tester.buffered("ButtonRelease"),
                     "a held button must not release itself")
        release_mouse("mouse_right")
        _assert_eq(tester.collect("ButtonRelease")[0]["button"], 3)
        return "button 3 held, then released, as two events"
    check("press_mouse holds the button until release_mouse", _split)


def check_scroll_events(tester: EventTester) -> None:
    """X11 encodes scrolling as buttons 4-7; the direction must pick correctly.

    On Linux the direction comes from the ``scroll_direction`` argument and
    the *sign of the value is discarded* — ``mouse_scroll`` takes ``abs()``
    on purpose, because a negative count used to make ``range()`` empty and
    scroll nothing at all. Windows and macOS read the direction off that same
    sign instead. The checks below pin the behaviour as measured rather than
    as one platform spells it; see Progress.md, where the difference is
    recorded as a decision for the maintainer.
    """
    from je_auto_control import mouse_scroll, set_mouse_position

    target = tester.centre()

    def _scroll(value: int, direction: str, expected_button: int) -> str:
        set_mouse_position(*target)
        tester.flush()
        mouse_scroll(value, scroll_direction=direction)
        presses = tester.collect("ButtonPress", abs(value))
        _assert_eq({event["button"] for event in presses}, {expected_button})
        return (f"{direction} x{abs(value)} arrived as button "
                f"{expected_button}")

    check("scroll_direction='scroll_up' arrives as button 4",
          lambda: _scroll(2, "scroll_up", 4))
    check("scroll_direction='scroll_down' arrives as button 5",
          lambda: _scroll(2, "scroll_down", 5))
    check("scroll_direction='scroll_left' arrives as button 6",
          lambda: _scroll(1, "scroll_left", 6))
    check("scroll_direction='scroll_right' arrives as button 7",
          lambda: _scroll(1, "scroll_right", 7))

    def _sign_is_ignored() -> str:
        set_mouse_position(*target)
        tester.flush()
        # Portable code written against the Windows sign convention lands
        # here. It does not scroll up; it scrolls down. That is the measured
        # contract, and this is what would go red if it ever changed.
        mouse_scroll(-2, scroll_direction="scroll_down")
        presses = tester.collect("ButtonPress", 2)
        _assert_eq({event["button"] for event in presses}, {5})
        return "a negative count scrolls the named direction, not the opposite"
    check("the sign of the count does not pick the direction on Linux",
          _sign_is_ignored)


def check_key_events(tester: EventTester) -> None:
    """A keystroke must arrive with the keycode the table promised."""
    from je_auto_control import (
        keyboard_keys_table, press_keyboard_key, release_keyboard_key, write,
    )

    def _single() -> str:
        tester.flush()
        press_keyboard_key("a")
        press = tester.collect("KeyPress")[0]
        release_keyboard_key("a")
        release = tester.collect("KeyRelease")[0]
        # The table holds real X keycodes (keysym_to_keycode at import), so
        # this checks the whole name -> keysym -> keycode -> wire path.
        _assert_eq(press["keycode"], keyboard_keys_table["a"])
        _assert_eq(release["keycode"], keyboard_keys_table["a"])
        _assert_eq(press["keysym"], "a")
        return f"'a' arrived as keycode {press['keycode']}"
    check("press/release_keyboard_key deliver the mapped keycode", _single)

    def _string() -> str:
        tester.flush()
        write("xyz")
        presses = tester.collect("KeyPress", 3)
        _assert_eq([event["keysym"] for event in presses], ["x", "y", "z"])
        return "write('xyz') arrived as x, y, z in order"
    check("write() delivers each character in order", _string)


def main() -> int:
    print("=" * 72)
    print("AutoControl X11 verification — real X server, real clients")
    print("=" * 72)

    layout = read_layout()
    report_environment(layout)
    paint_root(layout)

    check_backend_selection()
    check_geometry(layout)
    check_pixels(layout)
    check_pointer(layout)

    with EventTester() as tester:
        note(f"event tester window {tester.window_id} at {tester.rect}")
        check_button_events(tester)
        check_scroll_events(tester)
        check_key_events(tester)

    print("-" * 72)
    print("NOT verifiable in this container, and why:")
    note("A negative layout origin — X11's root window is the union of every")
    note("  monitor and always starts at (0, 0). The Wayland job's second")
    note("  layout has no analogue here; this is a protocol difference.")
    note("The uinput input path — it needs /dev/uinput, which is the host's")
    note("  to grant. docker/ydotool_verify.py reads those events back off")
    note("  the kernel device instead.")

    return summarise()


def summarise() -> int:
    """Print the tally and return the number of failed checks.

    Shared with ``x11_window_verify.py``, which runs in the same session and
    reports through the same harness.
    """
    failed = [name for name, ok, _ in _results if not ok]
    print("=" * 72)
    print(f"{len(_results) - len(failed)}/{len(_results)} checks passed")
    for name in failed:
        print(f"  FAILED: {name}")
    print("=" * 72)
    return len(failed)


if __name__ == "__main__":
    sys.exit(main())
