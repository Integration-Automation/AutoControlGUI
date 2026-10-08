"""Measure what a real macOS runner lets AutoControl's backend actually do.

macOS is the one supported platform with no container to put it in, so this
runs directly on a ``macos-14`` GitHub runner (see
``.github/workflows/platform-smoke.yml``). It exists because the capability
matrix said "implementation" for every macOS row: the code was there and
nothing had ever run it on a Mac.

Two of the capabilities here are gated by TCC — macOS asks the *user* to
grant Screen Recording and Accessibility, and a headless CI runner has no
user to ask. Which of them a runner grants by default is not something to
guess at, and guessing is how the Wayland work lost time twice by recording a
desktop's refusal as a container's limitation. So this was measured first,
and the measurement was a surprise: **a macos-14 runner grants both**, and
every probe below passes on one. See :data:`EXPECTED`.

``--measure``
    Run every probe, print what happened, and exit 0. Nothing is asserted;
    the output is the measurement. This is how :data:`EXPECTED` is
    (re)populated when a runner image changes.

default
    Assert :data:`EXPECTED` — what the measurement showed the runner permits.
    Exit status is the number of checks that did not match, so a capability
    appearing or disappearing turns CI red and names it. This is what the
    workflow runs.

Assert mode refuses to pass while :data:`EXPECTED` is empty, because a gate
that asserts nothing reads as coverage that does not exist.

A probe is not asserted before a runner has measured it. A new one goes into
:data:`REPORTED`: it runs in both modes and its result is printed with the line
:data:`EXPECTED` would hold, but it cannot turn the job red. Once a run has
shown what the runner does, move it to :data:`PROBES` with that value.
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import subprocess  # nosec B404  # reason: runs pytest on two repository test files, fixed argv, no shell
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
HEADLESS_TESTS = "test/unit_test/headless"

#: What a ``macos-14`` runner was measured to permit, on 2026-08-19. Keys are
#: probe names; values are ``True`` (works), ``False`` (silently does nothing
#: or is refused), or a string naming the exception type it raises.
#:
#: The measurement was a surprise worth writing down: **a GitHub macOS runner
#: grants both Screen Recording and Accessibility to the interpreter**, so
#: every capability here works. Capture returns real pixels rather than the
#: black rectangle a refusal produces, ``CGEventPost`` moves the cursor and
#: the move reads back exactly, and the AX walk returns real elements. The
#: usual assumption — that CI cannot exercise a TCC-gated macOS API — is
#: wrong for this runner, which is why this is measured and not reasoned
#: about.
#:
#: If a future runner image tightens any of that, the mismatch turns this job
#: red and names the capability that changed, which is the point.
EXPECTED: Dict[str, Any] = {
    "backend-selection": True,
    "screen-size": True,
    "screenshot": True,
    "get-pixel": True,
    "mouse-position": True,
    "mouse-move": True,
    "keyboard-post": True,
    "accessibility-tree": True,
    # The one row here that a CI run measured rather than a local one: there
    # is no Mac in the loop where this is written. It is asserted True from
    # the same grant the rows above it were measured to have — an event tap
    # needs exactly the Accessibility permission `keyboard-post` already
    # proved is granted. If that reasoning is wrong the job says so, names
    # this probe, and prints how many events the tap actually saw.
    "recorder": True,
    # True means "the code answered", not "the runner had windows". Measured:
    # Quartz reports 5 on-screen windows on a macos-14 runner and *none* of
    # them is at the application layer — they are menu bar and system UI. So
    # the count is reported and not asserted.
    "window-management": True,
}

#: The real-framework tests the two "reuse" probes run, and how many results
#: each must produce. These already exist and already run on the macOS squares
#: of the headless suite; there a skip is a pass, and here it is not -- the
#: probe says whether the question was actually reached.
CLICK_STATE_TESTS: Tuple[List[str], int] = ([
    f"{HEADLESS_TESTS}/test_osx_mouse_click_state.py::test_a_real_event_takes_the_click_count_it_is_given",
    f"{HEADLESS_TESTS}/test_osx_mouse_click_state.py::test_the_real_double_click_interval_is_a_positive_number",
], 3)
MINIMISED_WINDOW_TESTS: Tuple[List[str], int] = ([
    f"{HEADLESS_TESTS}/test_window_backend_macos_real.py"
    "::test_a_really_minimised_window_is_found_listed_and_restored",
], 1)

#: A whole child pytest run, window included.
TEST_RUN_TIMEOUT = 180

#: How long the window server is given to reflect a posted modifier.
KEY_STATE_TIMEOUT = 3.0

#: How long the recorder's tap thread is given to see the posted events. Its
#: run loop advances in slices, so one slice is not enough to rely on.
RECORDER_SETTLE_SECONDS = 1.0

_results: List[Tuple[str, bool, str]] = []


def note(message: str) -> None:
    """Print an indented remark that is not a probe."""
    print(f"      {message}")


class Outcome:
    """What one probe did, in a form both modes can use."""

    def __init__(self, worked: bool, detail: str,
                 error: Optional[str] = None) -> None:
        self.worked = worked
        self.detail = detail
        self.error = error

    @property
    def key(self) -> Any:
        """The value :data:`EXPECTED` records for this outcome."""
        return self.error if self.error else self.worked

    def __str__(self) -> str:
        if self.error:
            return f"raised {self.error}: {self.detail}"
        return ("works — " if self.worked else "no effect — ") + self.detail


def probe(name: str, fn: Callable[[], Outcome]) -> Outcome:
    """Run one probe and record what it did, without judging it yet."""
    try:
        outcome = fn()
    except Exception as error:  # noqa: BLE001  # reason: measuring, not asserting
        outcome = Outcome(False, traceback.format_exc(limit=2).strip().replace(
            "\n", " | "), type(error).__name__)
    _results.append((name, outcome.worked, str(outcome)))
    print(f"      {name}: {outcome}")
    return outcome


# --- probes ----------------------------------------------------------------


def probe_backend() -> Outcome:
    """The wrapper must land on the macOS backend at all."""
    from je_auto_control.wrapper import platform_wrapper

    module = platform_wrapper.mouse.__name__
    return Outcome("osx" in module, module)


def probe_screen_size() -> Outcome:
    """Quartz reports the display size without any TCC grant."""
    from je_auto_control import screen_size

    width, height = screen_size()
    return Outcome(width > 0 and height > 0, f"{width}x{height}")


def probe_screenshot() -> Outcome:
    """Capture needs Screen Recording on 10.15+; a refusal is silent."""
    from je_auto_control import screen_size, screenshot

    width, height = screen_size()
    frame = screenshot()
    if frame is None or getattr(frame, "size", 0) == 0:
        return Outcome(False, "returned an empty frame")
    shape = f"{frame.shape[1]}x{frame.shape[0]}"
    # A refused capture comes back as a correctly-sized black rectangle
    # rather than an error, so size alone proves nothing.
    blank = bool((frame == 0).all())
    return Outcome(not blank,
                   f"{shape} against a {width}x{height} display"
                   + (", but every pixel is black" if blank else ""))


def probe_get_pixel() -> Outcome:
    """The single-pixel read goes through the same capture permission."""
    from je_auto_control import get_pixel

    pixel = get_pixel(10, 10)
    return Outcome(pixel is not None, repr(pixel))


def probe_mouse_position() -> Outcome:
    """Reading the cursor needs no grant; only moving it does."""
    from je_auto_control import get_mouse_position

    position = get_mouse_position()
    return Outcome(position is not None, repr(position))


def probe_mouse_move() -> Outcome:
    """CGEventPost is accepted whether or not it is allowed to take effect.

    So the move is measured by reading the cursor back, not by whether the
    call returned — a refused post raises nothing at all.
    """
    from je_auto_control import get_mouse_position, screen_size, set_mouse_position

    width, height = screen_size()
    target = (min(width - 5, 137), min(height - 5, 211))
    set_mouse_position(*target)
    landed = tuple(get_mouse_position() or (-1, -1))
    return Outcome(landed == target, f"asked {target}, cursor at {landed}")


def probe_keyboard() -> Outcome:
    """Key posting is the most restricted of all; measure, do not assume.

    Nothing here has focus, so what is measured is whether the post is
    accepted and the modifier state changes — not where the character went.

    The read is polled rather than taken once. Measured on a macos-14 runner,
    an immediate ``check_key_is_press`` after the post returned True on one
    run and False on the next: ``CGEventSourceKeyState`` reflects the window
    server's state, and the posted event has to reach it first. Reading once
    makes this probe a coin toss, and a gate that is a coin toss is worse
    than no gate.
    """
    from je_auto_control import check_key_is_press, press_keyboard_key, release_keyboard_key

    press_keyboard_key("shift")
    try:
        deadline = time.monotonic() + KEY_STATE_TIMEOUT
        held = False
        while time.monotonic() < deadline:
            held = bool(check_key_is_press("shift"))
            if held:
                break
            time.sleep(0.05)
    finally:
        release_keyboard_key("shift")
    return Outcome(held, f"check_key_is_press('shift') became {held!r} within "
                         f"{KEY_STATE_TIMEOUT}s")


def probe_accessibility() -> Outcome:
    """The AX tree needs Accessibility; without it the walk returns nothing."""
    from je_auto_control.utils.accessibility.backends import get_backend

    backend = get_backend()
    if not backend.available:
        return Outcome(False, f"backend {backend.name!r} reports unavailable")
    elements = backend.list_elements(max_results=5)
    return Outcome(bool(elements),
                   f"backend {backend.name!r} returned {len(elements)} elements")


def probe_recorder() -> Outcome:
    """Recording needs Accessibility, a live event tap, and real events in it.

    macOS shipped without a recorder for as long as the code did exist: the
    old listener built an ``NSApplication`` at import and stopped recording
    with ``AppHelper.runEventLoop()``, so wiring it up would have put both on
    the path of ``import je_auto_control``. It now captures through a
    listen-only ``CGEventTap`` on its own thread, and this is where that gets
    exercised against a real window server rather than a fake.

    Three things have to hold together and only a Mac can answer any of them:
    the tap can be created at all (that is the Accessibility grant), events
    posted into the session reach it, and what comes back out carries the
    coordinates and the release — not just the press.
    """
    import je_auto_control as ac
    from je_auto_control.wrapper import platform_wrapper

    if platform_wrapper.recorder is None:
        return Outcome(False, "no recorder is selected on this platform")

    target = (321, 123)
    ac.record()
    try:
        # Posted through the public API, so this exercises the same path a
        # user's session does rather than a private Quartz call.
        ac.set_mouse_position(*target)
        ac.click_mouse("mouse_left", *target)
        ac.press_keyboard_key("a")
        ac.release_keyboard_key("a")
        # The tap thread runs the loop in slices; give it more than one.
        time.sleep(RECORDER_SETTLE_SECONDS)
    finally:
        events = ac.stop_record_timeline()

    operations = [event.get("op") for event in events]
    clicks = [event for event in events if event.get("op") == "mouse_down"]
    landed = [(event.get("x"), event.get("y")) for event in clicks]
    return Outcome(
        "mouse_down" in operations and "mouse_up" in operations
        and "key_down" in operations and target in landed,
        f"{len(events)} event(s): {operations}; clicks landed at {landed}, "
        f"posted {target}")


def probe_window_management() -> Outcome:
    """Quartz lists windows without a grant; acting on one needs Accessibility.

    What is asserted is that the *code* answers — the backend is selected, the
    Quartz query runs, and every window it returns can be described. What is
    only *reported* is how many there are, because that is a property of the
    runner's session rather than of this project: a GitHub macOS runner was
    measured to have no ordinary application windows at all. Gating on a
    count would go red the day the runner image happens to open one.
    """
    import je_auto_control as ac
    from je_auto_control.wrapper.window_backends import get_backend

    backend = get_backend()
    if not backend.available:
        return Outcome(False, f"backend {backend.name!r} reports unavailable")
    # Before the layer filter, so "the session is empty" and "the filter
    # dropped everything" are told apart rather than guessed at.
    raw = len(backend._window_info())
    windows = ac.list_windows()
    described = []
    for window_id, title in windows[:3]:
        described.append((title, backend.window_rect(window_id),
                          backend.window_process_id(window_id)))
    complete = all(rect is not None and pid > 0
                   for _title, rect, pid in described)
    return Outcome(complete,
                   f"{raw} on-screen window(s) from Quartz, {len(windows)} at "
                   f"the application layer; described {described}")


_REPORT_LINE = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED)\b(.*)$", re.MULTILINE)


def tally_test_report(output: str) -> Tuple[Dict[str, int], List[str]]:
    """Count the ``-rA`` summary lines of a pytest run; also the skip reasons."""
    counts = {"PASSED": 0, "FAILED": 0, "ERROR": 0, "SKIPPED": 0}
    skipped: List[str] = []
    for kind, rest in _REPORT_LINE.findall(output):
        # A skip line is "SKIPPED [n] file:line: reason" and stands for n tests.
        many = re.match(r"\s*\[(\d+)\]\s*(.*)$", rest) if kind == "SKIPPED" else None
        counts[kind] += int(many.group(1)) if many else 1
        if many:
            skipped.append(many.group(2).strip())
    return counts, skipped


def run_existing_tests(node_ids: List[str], wanted: int) -> Outcome:
    """Run tests the suite already has; works only if all ``wanted`` really passed.

    The real-window test asks to be invited (``AUTOCONTROL_REAL_WINDOW_TEST``):
    it opens a window. This script already moves the cursor and types, so it
    is the invitation.
    """
    env = dict(os.environ, AUTOCONTROL_REAL_WINDOW_TEST="1")
    done = subprocess.run(  # nosec B603  # nosemgrep  # reason: this interpreter, repository test ids, no shell
        [sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider", *node_ids],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=TEST_RUN_TIMEOUT, check=False)
    output = done.stdout + done.stderr
    counts, skipped = tally_test_report(output)
    detail = (f"{counts['PASSED']} passed, {counts['SKIPPED']} skipped, "
              f"{counts['FAILED'] + counts['ERROR']} failed of {wanted} "
              f"(pytest exit {done.returncode})")
    if skipped:
        detail += f"; skipped because: {' / '.join(skipped)}"
    if sum(counts.values()) == 0:
        detail += f"; no test ran: {output.strip()[-300:]!r}"
    worked = (counts["PASSED"] == wanted
              and counts["FAILED"] + counts["ERROR"] + counts["SKIPPED"] == 0)
    return Outcome(worked, detail)


def probe_click_state() -> Outcome:
    """A real Quartz mouse event keeps the click count written into it.

    Built and read back, never posted: it says the field holds the number,
    not that an application treats the click as a double-click.
    """
    return run_existing_tests(*CLICK_STATE_TESTS)


def probe_minimised_window() -> Outcome:
    """A window minimised through the backend is still found by id, and restored.

    The by-id Quartz query did not return a window its own process had just
    minimised the first time this ran on a runner, which is why
    ``_info_for`` falls back to the full list. The test opens a window of its
    own in a child process and puts it through the real frameworks.
    """
    return run_existing_tests(*MINIMISED_WINDOW_TESTS)


def judge_logical_frame(frame: Tuple[Tuple[int, int], Tuple[int, int]],
                        displays: List[Tuple[int, int, int, int]],
                        region: Tuple[Tuple[int, int], Tuple[int, int]],
                        asked: Tuple[int, int, int, int]) -> bool:
    """Whether a capture is in points: the frame is the displays, the region is itself.

    ``frame`` and ``region`` are ``(size, origin)`` as ``grab_logical`` gave
    them; ``displays`` are Quartz's bounds in points. On a runner's single 1x
    display that means the display's size at origin ``(0, 0)``.
    """
    if not displays:
        return False
    left = min(rect[0] for rect in displays)
    top = min(rect[1] for rect in displays)
    right = max(rect[0] + rect[2] for rect in displays)
    bottom = max(rect[1] + rect[3] for rect in displays)
    whole = ((right - left, bottom - top), (left, top))
    return frame == whole and region == ((asked[2], asked[3]), (asked[0], asked[1]))


def probe_grab_logical() -> Outcome:
    """``grab_logical`` returns points: the display's bounds, origin ``(0, 0)``.

    Written against fakes and never run on a Mac. What a runner can say is
    limited to its one 1x display, where points and pixels are the same
    number: that ``screencapture -R`` accepts the rectangle Quartz reports,
    that the frame is exactly ``CGDisplayBounds`` in size with its origin at
    the main display's corner, that a region comes back at its own size and
    origin, and what Pillow hands back for ``scale_down=True`` before this
    package resizes anything. Retina and a second display stay unmeasured.
    """
    import Quartz
    from PIL import ImageGrab

    import je_auto_control as ac
    from je_auto_control.utils.monitor_layout.macos_frame import quartz_display_bounds

    displays = quartz_display_bounds()
    main_id = Quartz.CGMainDisplayID()
    main = Quartz.CGDisplayBounds(main_id)
    points = (int(main.size.width), int(main.size.height))
    pixels = (int(Quartz.CGDisplayPixelsWide(main_id)), int(Quartz.CGDisplayPixelsHigh(main_id)))
    image, origin_x, origin_y = ac.grab_logical()
    asked = (10, 20, 64, 48)
    part, part_x, part_y = ac.grab_logical(asked)
    raw = ImageGrab.grab(bbox=(0, 0, points[0], points[1]), scale_down=True)
    blank = image.convert("L").getextrema() == (0, 0)
    worked = (not blank and judge_logical_frame(
        (tuple(image.size), (origin_x, origin_y)), displays,
        (tuple(part.size), (part_x, part_y)), asked))
    return Outcome(
        worked,
        f"frame {tuple(image.size)} at {(origin_x, origin_y)}; {len(displays)} display(s) {displays}; "
        f"main display {points} points, {pixels} pixels; region {asked} came back "
        f"{tuple(part.size)} at {(part_x, part_y)}; Pillow scale_down gave {tuple(raw.size)} for {points}"
        + ("; every pixel is black" if blank else ""))


PROBES: List[Tuple[str, Callable[[], Outcome]]] = [
    ("backend-selection", probe_backend),
    ("screen-size", probe_screen_size),
    ("screenshot", probe_screenshot),
    ("get-pixel", probe_get_pixel),
    ("mouse-position", probe_mouse_position),
    ("mouse-move", probe_mouse_move),
    ("keyboard-post", probe_keyboard),
    ("accessibility-tree", probe_accessibility),
    ("recorder", probe_recorder),
    ("window-management", probe_window_management),
]

#: Probes no runner has measured yet: run and printed in both modes, judged in
#: neither. Each was written on Windows, against the tests or fakes it names.
#:
#: ``click-state-readback`` and ``minimised-window-by-id`` re-run tests that
#: did pass on macos-14 inside the headless suite (2026-10-09, Python 3.10 and
#: 3.14) -- but as a child pytest of *this* job, with a skip counted as "did
#: not work", they have not run anywhere. ``grab-logical-points`` has never
#: executed on a Mac at all.
REPORTED: List[Tuple[str, Callable[[], Outcome]]] = [
    ("click-state-readback", probe_click_state),
    ("minimised-window-by-id", probe_minimised_window),
    ("grab-logical-points", probe_grab_logical),
]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--measure", action="store_true",
        help="report what the runner permits and exit 0, asserting nothing")
    options = parser.parse_args(argv)

    print("=" * 72)
    print("AutoControl macOS verification — real macOS, real window server")
    print("=" * 72)
    note(f"{platform.platform()}  python {platform.python_version()}")
    print("-" * 72)

    outcomes = {name: probe(name, fn) for name, fn in PROBES}
    print("-" * 72)
    print("reported, not asserted — no runner has measured these yet:")
    reported = {name: probe(name, fn) for name, fn in REPORTED}

    print("-" * 72)
    if options.measure:
        _print_measurement({**outcomes, **reported})
        return 0

    if not EXPECTED:
        print("EXPECTED is empty, so there is nothing to assert. Run with")
        print("--measure first and fill it in; passing here would mean")
        print("nothing and would read as coverage that does not exist.")
        print("=" * 72)
        return 1

    changed = _changed(outcomes)
    misfiled = [f"{name}: is in both REPORTED and EXPECTED; move it to PROBES"
                for name in reported if name in EXPECTED]
    print(f"{len(outcomes) - len(changed)}/{len(outcomes)} probes match "
          f"what this runner was measured to permit")
    for line in changed + misfiled:
        print(f"  CHANGED: {line}")
    if reported:
        print("measured but not asserted; to make one a gate, move it from")
        print("REPORTED to PROBES and add its line to EXPECTED:")
        for name, outcome in reported.items():
            print(f'    "{name}": {outcome.key!r},')
    print("=" * 72)
    return len(changed) + len(misfiled)


def _print_measurement(outcomes: Dict[str, Outcome]) -> None:
    """``--measure``: the lines :data:`EXPECTED` would hold, nothing judged."""
    print("measurement only — nothing asserted. EXPECTED would be:")
    print()
    for name, outcome in outcomes.items():
        print(f'    "{name}": {outcome.key!r},')
    print()
    print("Paste that into EXPECTED and drop --measure to make it a gate.")
    print("=" * 72)


def _changed(outcomes: Dict[str, Outcome]) -> List[str]:
    """One line per asserted probe that did not do what :data:`EXPECTED` says."""
    lines = []
    for name, outcome in outcomes.items():
        if name not in EXPECTED:
            lines.append(f"{name}: not in EXPECTED (a new probe?)")
        elif outcome.key != EXPECTED[name]:
            lines.append(
                f"{name}: expected {EXPECTED[name]!r}, measured {outcome.key!r}")
    return lines


if __name__ == "__main__":
    sys.exit(main())
