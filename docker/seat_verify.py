"""Verify where ydotool's absolute move actually puts the cursor.

The other four verification images each answer one half of the Wayland input
story and stop at the same wall. ``docker/Dockerfile.wayland`` runs a real
wlroots compositor but consumes no input devices; ``docker/Dockerfile.ydotool``
reads ydotool's events straight off the kernel with no compositor at all. So
what ``mousemove --absolute`` *puts on the wire* is settled, and what a
compositor *does with it* was recorded in ``Progress.md`` as needing a VM with
"a compositor that consumes libinput devices".

It does not need one, for the third time in this project's history. wlroots
takes ``WLR_BACKENDS=headless,libinput``: the outputs stay virtual while the
input side is the real libinput backend, and libseat's builtin backend opens
the devices directly once ``SEATD_VTBOUND=0`` stops it reaching for a VT that
a container has no business owning. ydotoold's uinput device is then an
ordinary seat device like any mouse, and ``grim -c`` composites the cursor
into a screenshot — so the compositor answers, in layout coordinates, the
question this file exists to ask:

  **Does ``ydotool mousemove --absolute -x X -y Y`` put the cursor at layout
  ``(X, Y)``?**

No, twice over:

* Its origin is the corner the compositor clamps to, which is the top-left of
  the *output layout*. That is layout ``(0, 0)`` only while every output sits
  at a non-negative position; on the layout every desktop with a monitor left
  of the primary one has, the two differ by the layout origin. That is the
  translation :func:`je_auto_control.linux_wayland.mouse._ydotool_point` now
  applies, and this file is where the number comes from.
* The displacement is relative motion, so the compositor's pointer
  acceleration scales it. Under libinput's default adaptive profile the
  cursor moves twice as far from that corner as asked. ydotool's own
  ``--help`` says "You need to disable mouse speed acceleration for correct
  absolute movement"; this measures what ignoring that costs.

**What a screenshot can see is the cursor's image, not its hotspot**, and the
two differ by whatever offset the cursor theme declares. Nothing here depends
on that offset: every claim is a difference between two captures, a distance
that the offset cancels out of, or an output the cursor is unambiguously
inside. The one absolute reading — that a move to ``(0, 0)`` draws the cursor
flush into the layout's very first pixel — is the clamp pinning it there,
which is exactly the claim being made.

Exit status is the number of failed checks.
"""
from __future__ import annotations

import json
import os
import subprocess  # nosec B404  # reason: argv-list, fixed tool names, no shell
import sys
import tempfile
import time
import traceback
from typing import Any, Callable, List, Optional, Tuple

import numpy
from PIL import Image

_results: List[Tuple[str, bool]] = []

Point = Tuple[int, int]

#: The solid colour ``entrypoint-seat.sh`` paints each output. Anything else
#: in a capture is the cursor: nothing else is ever on screen. Keyed by name
#: because sway lists its outputs in whatever order it likes.
OUTPUT_COLOURS = {
    "HEADLESS-1": (0x12, 0x34, 0x56),
    "HEADLESS-2": (0xAB, 0xCD, 0xEF),
}

#: How long to let a move settle before capturing. ydotool's own start delay
#: is 100 ms; the rest is the compositor's next frame.
_SETTLE_SECONDS = 0.6

#: The cursor image is drawn from its hotspot by at most this many pixels on
#: either axis, so a reading is "the same pixel" within it. Only used where a
#: check compares a drawn position against a requested coordinate directly;
#: every other check is a difference, which the offset cancels out of.
_CURSOR_IMAGE_SLACK = 2

#: libinput's maximum acceleration factor for the adaptive profile at the
#: default speed of 0. ``--absolute`` sends both of its events in a single
#: frame, so the velocity saturates the profile and the factor lands here.
_ADAPTIVE_MAX_FACTOR = 2


def _scratch_dir() -> str:
    """A private directory for the capture, created 0700 if it is not there.

    The image sets ``XDG_RUNTIME_DIR``; without it — running this by hand —
    a fresh ``mkdtemp``, rather than a predictable name under the ``/tmp``
    root that any user on the host can create entries in.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        os.makedirs(runtime, mode=0o700, exist_ok=True)
        return runtime
    return tempfile.mkdtemp(prefix="autocontrol-seat-verify-")


CAPTURE = os.path.join(_scratch_dir(), "seat-capture.png")


def check(name: str, fn: Callable[[], Any]) -> Any:
    try:
        detail = fn()
    except Exception:  # noqa: BLE001  # reason: one failed check must not stop the rest
        _results.append((name, False))
        print(f"FAIL  {name}")
        print("        " + traceback.format_exc(limit=4).strip().replace(
            "\n", "\n        "))
        return None
    _results.append((name, True))
    print(f"ok    {name}" + (f"  — {detail}" if detail else ""))
    return detail


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _run(argv: List[str], *, timeout: float = 10.0) -> str:
    """Run a tool from this image and return its stdout."""
    # argv is assembled from literals in this file; no shell, no user input.
    completed = subprocess.run(argv, check=True,  # nosec B603  # nosemgrep
                               timeout=timeout,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    return completed.stdout.decode("utf-8", errors="replace")


def _minus(left: Point, right: Point) -> Point:
    return (left[0] - right[0], left[1] - right[1])


def _plus(left: Point, right: Point) -> Point:
    return (left[0] + right[0], left[1] + right[1])


# --------------------------------------------------------------------------
# The layout, straight out of the compositor
# --------------------------------------------------------------------------

class Layout:
    """The output layout sway reports, as this verification's ground truth.

    Read from sway's IPC rather than from AutoControl's own ``wlr-randr``
    parser, so that agreeing with it is a check rather than a tautology.
    """

    def __init__(self, outputs: List[Tuple[str, int, int, int, int]]) -> None:
        _require(bool(outputs), "sway reported no active outputs")
        self.outputs = outputs
        self.rects = [rect for _, *rect in outputs]
        self.origin: Point = (min(x for x, _, _, _ in self.rects),
                              min(y for _, y, _, _ in self.rects))

    def output_at(self, x: int, y: int) -> Optional[str]:
        """Name of the output containing ``(x, y)``, or None."""
        for name, left, top, width, height in self.outputs:
            if left <= x < left + width and top <= y < top + height:
                return name
        return None

    def far_from(self, x: int, y: int) -> Point:
        """A point on another output, to park the cursor well out of the way."""
        for name, left, top, _, _ in self.outputs:
            if name != self.output_at(x, y):
                return (left + 600, top + 500)
        return (x + 400, y + 400)

    def __str__(self) -> str:
        return " + ".join(f"{name} {w}x{h}@({x},{y})"
                          for name, x, y, w, h in self.outputs)


def read_layout() -> Layout:
    """Ask sway for its outputs."""
    outputs = json.loads(_run(["swaymsg", "-r", "-t", "get_outputs"]))
    return Layout([
        (str(item["name"]),
         int(item["rect"]["x"]), int(item["rect"]["y"]),
         int(item["rect"]["width"]), int(item["rect"]["height"]))
        for item in outputs if item.get("active")
    ])


def pointer_devices() -> List[str]:
    """Names of every pointer sway's libinput backend is holding."""
    inputs = json.loads(_run(["swaymsg", "-r", "-t", "get_inputs"]))
    return [item.get("name", "") for item in inputs
            if item.get("type") == "pointer"]


def set_pointer_acceleration(profile: str, speed: str) -> None:
    """Reconfigure every pointer, then let the change settle."""
    _run(["swaymsg", f"input type:pointer accel_profile {profile}"])
    _run(["swaymsg", f"input type:pointer pointer_accel {speed}"])
    time.sleep(0.2)


# --------------------------------------------------------------------------
# Where the cursor was drawn, in layout coordinates
# --------------------------------------------------------------------------

def drawn_cursor(layout: Layout) -> Point:
    """Layout coordinate of the drawn cursor's top-left pixel.

    ``grim -c`` composites the cursor into a capture of the whole layout,
    whose first pixel is the layout origin. The outputs carry two flat
    colours, so every other pixel belongs to the cursor.
    """
    _run(["grim", "-c", CAPTURE])
    with Image.open(CAPTURE) as raw:
        frame = numpy.asarray(raw.convert("RGB"))
    background = numpy.zeros(frame.shape[:2], dtype=bool)
    for colour in OUTPUT_COLOURS.values():
        background |= (frame == numpy.array(colour, dtype=frame.dtype)).all(-1)
    rows, columns = numpy.nonzero(~background)
    _require(rows.size > 0,
             "no cursor was drawn: the capture is entirely background, so "
             "either the compositor has no cursor theme or grim -c did not "
             "composite one")
    return _plus(layout.origin, (int(columns.min()), int(rows.min())))


# --------------------------------------------------------------------------
# The two ways to ask for a move
# --------------------------------------------------------------------------

def ydotool_absolute(x: int, y: int) -> None:
    """The raw CLI call, with no translation of any kind."""
    _run(["ydotool", "mousemove", "--absolute", "-x", str(x), "-y", str(y)])


def autocontrol_set_position(x: int, y: int) -> None:
    """The backend's own entry point, translation included."""
    from je_auto_control.linux_wayland import mouse
    mouse.set_position(x, y)


def land(move: Callable[[int, int], None], layout: Layout,
         point: Point) -> Point:
    """Ask ``move`` for ``point`` and report where the cursor was drawn."""
    move(*point)
    time.sleep(_SETTLE_SECONDS)
    return drawn_cursor(layout)


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def _seat_holds_the_device(names: List[str]) -> str:
    _require(any("ydotool" in name.lower() for name in names),
             f"sway is holding no ydotool pointer; it has {names}. Without "
             "one the libinput backend never picked the device up and "
             "nothing below would be measuring a compositor at all.")
    return ", ".join(names)


def _origin_is_the_layout_corner(layout: Layout) -> str:
    """``--absolute 0 0`` drives the cursor into the layout's first pixel.

    The clamp holds it there and clips the image against the edge, so the
    drawn position is the corner itself with no theme offset in the way.
    """
    drawn = land(ydotool_absolute, layout, (0, 0))
    _require(drawn == layout.origin,
             f"--absolute -x 0 -y 0 drew the cursor at {drawn}, expected it "
             f"flush into the layout corner {layout.origin}")
    return f"(0, 0) -> {drawn}, the layout's first pixel"


def _moves_one_pixel_per_pixel(layout: Layout, near: Point,
                               far: Point) -> str:
    """With acceleration off, the displacement is the one that was asked for."""
    drawn_near = land(ydotool_absolute, layout, near)
    drawn_far = land(ydotool_absolute, layout, far)
    _require(_minus(drawn_far, drawn_near) == _minus(far, near),
             f"asking for {near} then {far} moved the cursor "
             f"{_minus(drawn_far, drawn_near)}, expected {_minus(far, near)}")
    return f"{near} -> {far} moved {_minus(drawn_far, drawn_near)}"


def _counts_from_the_corner(layout: Layout, point: Point) -> str:
    """The requested offset is measured from the corner, not from (0, 0)."""
    drawn = land(ydotool_absolute, layout, point)
    expected = _plus(layout.origin, point)
    distance = _minus(drawn, expected)
    _require(max(abs(distance[0]), abs(distance[1])) <= _CURSOR_IMAGE_SLACK,
             f"--absolute -x {point[0]} -y {point[1]} drew the cursor at "
             f"{drawn}, which is {distance} from the corner plus the offset "
             f"{expected}")
    return f"{point} -> {drawn}, corner + {point} within {distance}"


def _an_untranslated_zero_misses_its_monitor(layout: Layout) -> str:
    """The failure this translation exists to prevent, made concrete."""
    if layout.origin == (0, 0):
        return "not applicable: this layout's corner is layout (0, 0)"
    drawn = land(ydotool_absolute, layout, (0, 0))
    reached = layout.output_at(*drawn)
    intended = layout.output_at(0, 0)
    _require(reached is not None and intended is not None
             and reached != intended,
             f"expected an untranslated (0, 0) to reach a different output "
             f"than layout (0, 0); it drew at {drawn} on output {reached} "
             f"while layout (0, 0) is on output {intended}")
    return (f"reaches output {reached} at {drawn}, while layout (0, 0) is on "
            f"output {intended} — {abs(layout.origin[0])} px apart")


def _acceleration_scales_the_move(layout: Layout, near: Point,
                                  far: Point) -> str:
    """Under the default profile the displacement is not the one asked for."""
    drawn_near = land(ydotool_absolute, layout, near)
    drawn_far = land(ydotool_absolute, layout, far)
    moved = _minus(drawn_far, drawn_near)
    asked = _minus(far, near)
    _require(moved != asked,
             f"asking for {near} then {far} moved the cursor exactly {moved} "
             "under the default adaptive profile, so this image is no longer "
             "measuring pointer acceleration at all")
    return f"asked {asked}, moved {moved}"


def _acceleration_factor_is_two(layout: Layout, near: Point,
                                far: Point) -> str:
    """Pin today's number, so a libinput change is loud rather than silent."""
    drawn_near = land(ydotool_absolute, layout, near)
    drawn_far = land(ydotool_absolute, layout, far)
    moved = _minus(drawn_far, drawn_near)
    asked = _minus(far, near)
    expected = (asked[0] * _ADAPTIVE_MAX_FACTOR,
                asked[1] * _ADAPTIVE_MAX_FACTOR)
    _require(moved == expected,
             f"expected libinput's adaptive profile to saturate at "
             f"{_ADAPTIVE_MAX_FACTOR}x — {asked} becoming {expected} — but "
             f"the cursor moved {moved}")
    return f"{asked} became {moved}, {_ADAPTIVE_MAX_FACTOR}x on both axes"


def _backend_agrees_with_the_compositor(layout: Layout) -> str:
    """AutoControl reads the same origin the compositor reports."""
    from je_auto_control.linux_wayland import screen
    reported = screen.layout_origin()
    _require(reported == layout.origin,
             f"screen.layout_origin() says {reported}, sway says "
             f"{layout.origin}")
    return f"{reported}"


def _set_position_subtracts_exactly_the_origin(layout: Layout,
                                               point: Point) -> str:
    """The backend's translation is the layout origin and nothing else.

    Comparing the two paths against each other rather than against a
    coordinate keeps the cursor theme out of it entirely: whatever offset the
    drawn image carries is the same in both captures.
    """
    through_backend = land(autocontrol_set_position, layout, point)
    raw = land(ydotool_absolute, layout, _minus(point, layout.origin))
    _require(through_backend == raw,
             f"set_position{point} drew at {through_backend} while the raw "
             f"CLI asked for {_minus(point, layout.origin)} drew at {raw}")
    return f"set_position{point} == --absolute{_minus(point, layout.origin)}"


def _set_position_lands_on_the_layout_pixel(layout: Layout,
                                            point: Point) -> str:
    """Ask in layout coordinates, land on that pixel."""
    drawn = land(autocontrol_set_position, layout, point)
    distance = _minus(drawn, point)
    _require(max(abs(distance[0]), abs(distance[1])) <= _CURSOR_IMAGE_SLACK,
             f"mouse.set_position{point} drew the cursor at {drawn}, "
             f"{distance} away")
    _require(layout.output_at(*drawn) == layout.output_at(*point),
             f"mouse.set_position{point} landed on output "
             f"{layout.output_at(*drawn)}, not {layout.output_at(*point)}")
    return f"{point} -> drawn at {drawn}"


def _software_cursor_lands_in_the_capture(layout: Layout,
                                          point: Point) -> str:
    """Record that a capture asked for no cursor contains one anyway.

    ``grim`` is invoked without ``-c`` here and everywhere else in the
    project, so the request is right; what comes back is not. wlroots draws a
    *software* cursor whenever the backend has no cursor plane — always on
    headless, and on any DRM session where the driver refuses one or the user
    set ``WLR_NO_HARDWARE_CURSORS=1`` — and a software cursor is composited
    into the output buffer that ``wlr-screencopy`` then hands over. Every
    locator, template match and OCR read in this project goes through that
    capture, so on such a session the pointer punches a pointer-shaped hole
    in whatever it is sitting on.

    Asserted the way it measures rather than the way it ought to be: a
    wlroots that starts honouring ``overlay_cursor`` for software cursors
    will fail this check, which is the notification this project wants.
    """
    from je_auto_control.linux_wayland import screen
    land(autocontrol_set_position, layout, point)
    under_cursor = tuple(screen.get_pixel(*point))
    land(autocontrol_set_position, layout, layout.far_from(*point))
    uncovered = tuple(screen.get_pixel(*point))
    named = layout.output_at(*point)
    _require(uncovered == OUTPUT_COLOURS[named],
             f"with the pointer parked elsewhere, get_pixel{point} returned "
             f"{uncovered} rather than {named}'s {OUTPUT_COLOURS[named]}")
    _require(under_cursor != uncovered,
             f"get_pixel{point} returned {uncovered} with the pointer both "
             "on that pixel and away from it. If this compositor has started "
             "honouring the no-overlay request for software cursors, the "
             "caveat recorded in docs/CAPABILITY_MATRIX.md and the READMEs "
             "can go, along with cursor_may_be_captured in the diagnostics "
             "bundle.")
    return (f"{under_cursor} under the pointer vs {uncovered} without it — "
            "the capture is not cursor-free")


def _input_and_capture_address_one_pixel(layout: Layout, point: Point) -> str:
    """``set_position`` and ``get_pixel`` have to mean the same point.

    The pointer is parked elsewhere before the pixel is read: on a compositor
    drawing a software cursor the capture would otherwise return the cursor's
    own colour, which is a different measurement from this one.
    """
    from je_auto_control.linux_wayland import screen
    drawn = land(autocontrol_set_position, layout, point)
    reached = layout.output_at(*drawn)
    land(autocontrol_set_position, layout, layout.far_from(*point))
    colour = tuple(screen.get_pixel(*point))
    named = layout.output_at(*point)
    _require(named is not None, f"{point} is on no output")
    _require(reached == named,
             f"the pointer reached {reached} while the pixel was read on "
             f"{named}")
    _require(colour == OUTPUT_COLOURS[named],
             f"get_pixel{point} returned {colour}, but {named} is painted "
             f"{OUTPUT_COLOURS[named]}")
    return f"both reach {named}, painted {colour}"


# --------------------------------------------------------------------------

def _interior_points(layout: Layout) -> List[Point]:
    """One point per output, far enough inside that no edge can clip it."""
    return [(x + 120, y + 90) for x, y, _, _ in layout.rects]


def main() -> int:
    os.environ.setdefault("JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND", "cli")

    layout = read_layout()
    print(f"layout: {layout}   origin {layout.origin}\n")

    check("sway's libinput backend is holding the ydotool device",
          lambda: _seat_holds_the_device(pointer_devices()))

    # Everything about the origin is measured with acceleration switched off,
    # because a scaled move cannot show where it counted from.
    set_pointer_acceleration("flat", "0")

    check("--absolute counts from the layout corner, not layout (0, 0)",
          lambda: _origin_is_the_layout_corner(layout))
    check("with acceleration off the move is one pixel per pixel",
          lambda: _moves_one_pixel_per_pixel(layout, (50, 50), (600, 400)))
    check("a 500x300 request lands 500x300 from that corner",
          lambda: _counts_from_the_corner(layout, (500, 300)))
    check("an untranslated (0, 0) misses the monitor it names",
          lambda: _an_untranslated_zero_misses_its_monitor(layout))

    check("screen.layout_origin() matches the compositor's own layout",
          lambda: _backend_agrees_with_the_compositor(layout))
    for point in _interior_points(layout):
        check(f"set_position{point} subtracts exactly the layout origin",
              lambda p=point: _set_position_subtracts_exactly_the_origin(
                  layout, p))
        check(f"set_position{point} lands on that layout pixel",
              lambda p=point: _set_position_lands_on_the_layout_pixel(
                  layout, p))
    check("set_position and get_pixel address the same monitor",
          lambda: _input_and_capture_address_one_pixel(
              layout, _interior_points(layout)[0]))
    check("a software cursor lands in a capture that asked for none",
          lambda: _software_cursor_lands_in_the_capture(
              layout, _interior_points(layout)[0]))

    # And with the compositor's default profile back, what the option name
    # promises stops being true at all.
    set_pointer_acceleration("adaptive", "0")
    check("the default profile scales the move, so it is not absolute",
          lambda: _acceleration_scales_the_move(layout, (50, 50), (300, 200)))
    check("that scaling is libinput's 2x adaptive ceiling today",
          lambda: _acceleration_factor_is_two(layout, (50, 50), (300, 200)))

    failed = [name for name, ok in _results if not ok]
    print("\n" + "=" * 70)
    print(f"{len(_results) - len(failed)}/{len(_results)} checks passed")
    for name in failed:
        print(f"  failed: {name}")
    return len(failed)


if __name__ == "__main__":
    sys.exit(main())
