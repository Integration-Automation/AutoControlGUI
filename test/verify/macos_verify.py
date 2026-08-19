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
"""
from __future__ import annotations

import argparse
import platform
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

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
    "recorder-absent": True,
}

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

    Nothing here has focus, so what is being measured is whether the post is
    accepted and the modifier state changes — not where the character went.
    """
    from je_auto_control import check_key_is_press, press_keyboard_key, release_keyboard_key

    press_keyboard_key("shift")
    try:
        held = check_key_is_press("shift")
    finally:
        release_keyboard_key("shift")
    return Outcome(bool(held), f"check_key_is_press('shift') returned {held!r}")


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
    """macOS ships no recorder, and must say so rather than look broken.

    ``osx/record/osx_record.py`` exists, but wiring it up would put an
    ``NSApplication`` and a blocking run loop into import of the platform
    wrapper, so ``recorder`` is None on purpose. This pins that it is a
    deliberate absence and not something that quietly stopped working.
    """
    from je_auto_control.wrapper import platform_wrapper

    return Outcome(platform_wrapper.recorder is None,
                   f"recorder is {platform_wrapper.recorder!r}")


PROBES: List[Tuple[str, Callable[[], Outcome]]] = [
    ("backend-selection", probe_backend),
    ("screen-size", probe_screen_size),
    ("screenshot", probe_screenshot),
    ("get-pixel", probe_get_pixel),
    ("mouse-position", probe_mouse_position),
    ("mouse-move", probe_mouse_move),
    ("keyboard-post", probe_keyboard),
    ("accessibility-tree", probe_accessibility),
    ("recorder-absent", probe_recorder),
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
    if options.measure:
        print("measurement only — nothing asserted. EXPECTED would be:")
        print()
        for name, outcome in outcomes.items():
            print(f'    "{name}": {outcome.key!r},')
        print()
        print("Paste that into EXPECTED and drop --measure to make it a gate.")
        print("=" * 72)
        return 0

    if not EXPECTED:
        print("EXPECTED is empty, so there is nothing to assert. Run with")
        print("--measure first and fill it in; passing here would mean")
        print("nothing and would read as coverage that does not exist.")
        print("=" * 72)
        return 1

    failed = []
    for name, outcome in outcomes.items():
        if name not in EXPECTED:
            failed.append(f"{name}: not in EXPECTED (a new probe?)")
        elif outcome.key != EXPECTED[name]:
            failed.append(
                f"{name}: expected {EXPECTED[name]!r}, measured {outcome.key!r}")
    print(f"{len(outcomes) - len(failed)}/{len(outcomes)} probes match "
          f"what this runner was measured to permit")
    for line in failed:
        print(f"  CHANGED: {line}")
    print("=" * 72)
    return len(failed)


if __name__ == "__main__":
    sys.exit(main())
