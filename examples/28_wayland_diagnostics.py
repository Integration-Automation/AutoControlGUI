"""Ask what this session can do, and what stands in the way when it cannot.

``22_wayland_backend.py`` shows which helper programs are installed. This one
asks the question that matters on Wayland: *can input, capture, recording and
the stop key be used right now, through which backend, and if not, what does
the operator do about it?*

    snapshot = ac.probe_capabilities()
    for capability in snapshot.capabilities:
        print(capability.name, capability.state.value, capability.backend)
        if capability.recovery:
            print("  ->", capability.recovery)

**The probe has no side effect.** It reads the environment, looks names up on
``PATH``, asks the loader whether a library exists and reads the authorisation
ledger. It never opens a portal request, never shows a consent dialog and
never sends an event, so it is safe from a health check or an MCP client. The
same data is ``AC_probe_capabilities`` in an action file, the
``ac_probe_capabilities`` MCP tool and the Diagnostics tab.

States worth recognising:

``not_requested``         usable; the desktop asks for consent on first use
``needs_permission``      someone refused, or a device node is not readable
``needs_setup``           something has to be installed or configured
``revoked``               the compositor took a granted session away
``compositor_restarted``  the grant came from a compositor that is gone
``unknown``               not determinable without side effects (macOS)

A refused or revoked consent is **not** worked around: input raises
``WaylandAuthorisationError`` instead of quietly switching to ``ydotool``,
until ``ac.reset_input_authorisation()`` (``AC_reset_input_authorisation``).

Recording is two different things on Wayland. What *this program* executed
needs no hook at all -- ``InputStepLog`` collects it on every backend. What the
*user* typed needs the kernel's event devices, which is opt-in per device
through ``JE_AUTOCONTROL_WAYLAND_RECORD_DEVICES`` (``PhysicalRecorder``).

Relevant settings::

    JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=auto|wayland|x11
    JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=auto|cli       # cli = ydotool, never the portal
    JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND="mytool {output}"   # your own capture tool
    JE_AUTOCONTROL_WAYLAND_RECORD_DEVICES=/dev/input/event3,/dev/input/event7
    JE_AUTOCONTROL_WAYLAND_EI_WORKER=1                  # libei in a helper process
    JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL=flat|strict    # ydotool absolute moves

``--validate`` describes four desktops from made-up contexts (so it gives the
same answer on Windows, macOS and Linux) and journals a dry run. Without the
flag the script probes the session it is running in, which is equally free of
side effects.
"""
import argparse
import sys
from typing import Dict, List, Optional

import je_auto_control as ac
# Only needed to *describe* a desktop; probing the real one takes no ledger.
from je_auto_control.linux_wayland.authorisation import (
    INPUT, AuthorisationLedger, AuthorisationState,
)

_WAYLAND_ENV = {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0",
                "XDG_RUNTIME_DIR": "/run/user/1000"}


def show(title: str, snapshot: ac.CapabilitySnapshot) -> None:
    """Print one snapshot as a small table."""
    print(f"{title}: platform={snapshot.platform} display={snapshot.display_server}"
          f" xwayland={snapshot.xwayland}")
    for capability in snapshot.capabilities:
        scope = "" if capability.desktop_wide else " (XWayland windows only)"
        print(f"  {capability.name:<13} {capability.state.value:<21} via {capability.backend}{scope}")
        if capability.recovery:
            print(f"      fix: {capability.recovery}")


def _context(environ: Dict[str, str], *, tools: tuple = (), libei: bool = False,
             bus: bool = True, ledger: Optional[AuthorisationLedger] = None,
             loaded: Optional[str] = None) -> ac.BackendContext:
    """A desktop described by hand: nothing here reads the real machine."""
    return ac.BackendContext(
        platform="linux", environ=environ,
        which=lambda name: f"/usr/bin/{name}" if name in tools else None,
        library_present=lambda name: libei and name in ("ei", "oeffis"),
        session_bus_present=lambda: bus, readable=lambda _path: False,
        compositor=lambda _environ: "8:1234:1",
        authorisations=ledger if ledger is not None else AuthorisationLedger(),
        loaded_backend=loaded)


def validate() -> int:
    """Probe four described desktops and check each reads the way it should."""
    refused = AuthorisationLedger()
    refused.transition(INPUT, AuthorisationState.DECLINED, "the user dismissed the dialog")
    desktops = {
        "GNOME, portal not asked yet": _context(
            _WAYLAND_ENV, tools=("gnome-screenshot",), libei=True),
        "GNOME, consent refused": _context(
            _WAYLAND_ENV, tools=("gnome-screenshot", "ydotool"), libei=True, ledger=refused),
        "sway with ydotool and grim": _context(
            {**_WAYLAND_ENV, "JE_AUTOCONTROL_WAYLAND_RECORD_DEVICES": "/dev/input/event3"},
            tools=("ydotool", "grim"), bus=False),
        "X11 backend on a Wayland session": _context(
            {**_WAYLAND_ENV, "DISPLAY": ":0"}, loaded="x11"),
    }
    snapshots = {title: ac.probe_capabilities(context) for title, context in desktops.items()}
    for title, snapshot in snapshots.items():
        show(title, snapshot)

    # What this program executes can be journalled with no input hook at all.
    # A dry run resolves every command without calling it.
    log = ac.InputStepLog()
    log.run([["AC_set_var", {"name": "greeting", "value": "hello"}],
             ["AC_get_var", {"name": "greeting"}]], dry_run=True)
    print(f"InputStepLog noted {len(log.steps)} step(s) from a dry run: "
          f"{[step[0] for step in log.steps]}")

    expected = {
        "GNOME, portal not asked yet": ("not_requested", "libei", True),
        # ydotool is installed, and is still not used: a refusal is not a fallback.
        "GNOME, consent refused": ("needs_permission", "libei", True),
        "sway with ydotool and grim": ("available", "ydotool", True),
        "X11 backend on a Wayland session": ("available", "xwayland", False),
    }
    problems: List[str] = []
    for title, wanted in expected.items():
        found = snapshots[title].input
        got = (found.state.value, found.backend, found.desktop_wide)
        if got != wanted:
            problems.append(f"{title}: input is {got}, expected {wanted}")
    if snapshots["sway with ydotool and grim"].get("recording").state.value != "needs_permission":
        problems.append("an unreadable recording device should read as needs_permission")
    if len(log.steps) != 2:
        problems.append(f"expected 2 journalled steps, got {len(log.steps)}")
    for problem in problems:
        print(f"FAILED: {problem}")
    print("validate:", "failed" if problems else "ok")
    return 1 if problems else 0


def main(argv: Optional[List[str]] = None) -> int:
    """Parse the command line; see the module docstring."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--validate", action="store_true",
                        help="probe described desktops instead of this one")
    args = parser.parse_args(argv)
    if args.validate:
        return validate()
    show("this session", ac.probe_capabilities())
    return 0


if __name__ == "__main__":
    sys.exit(main())
