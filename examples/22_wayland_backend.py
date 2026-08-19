"""Run AutoControl on a Wayland session.

AutoControl picks the Wayland backend automatically when it detects
``XDG_SESSION_TYPE=wayland`` or a ``WAYLAND_DISPLAY`` socket. Override
with::

    export JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11      # force XWayland
    export JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=wayland  # force Wayland
    export JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=auto     # default

The Wayland backend talks to three CLI bridges:

* ``wtype``  — keyboard text input (wlroots virtual-keyboard protocol)
* ``ydotool`` — keyboard key events + mouse (uinput via daemon)
* ``grim``   — screenshots (wlroots screencopy protocol)

Install whichever your distribution ships, e.g. on Debian / Ubuntu::

    sudo apt install wtype ydotool grim wlr-randr

Recording, global key listening, and per-window event injection are
*not* available on Wayland by design — those calls raise
``NotImplementedError`` with a hint pointing at the X11 fallback.

Two Wayland-only caveats are worth knowing before a script leans on them:

* ``ydotool mousemove --absolute`` is relative motion the compositor
  accelerates, so an absolute move through that fallback is pixel-exact only
  where pointer acceleration is off. The factor cannot be read back, so turn
  acceleration off for the ydotoold device and say so with
  ``JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL=flat``; ``=strict`` refuses such a
  move rather than mispositioning, and leaving it unset warns once per
  process and moves anyway. The libei path is absolute and unaffected.
* A capture may contain the mouse cursor. Nothing here asks for it, but
  wlroots composites a *software* cursor into the buffer screen capture hands
  back whenever the backend has no cursor plane. Windows and X11 never
  include the pointer, so park it away from whatever a locator, a template
  match or an OCR read is about to look at.
"""
from je_auto_control.linux_wayland import (
    is_wayland_session, missing_dependencies, select_display_server,
    WAYLAND_GRIM, WAYLAND_WTYPE, WAYLAND_YDOTOOL,
)


def main() -> None:
    print(f"detected display server: {select_display_server()}")
    print(f"is wayland session: {is_wayland_session()}")
    missing = missing_dependencies(
        [WAYLAND_WTYPE, WAYLAND_YDOTOOL, WAYLAND_GRIM],
    )
    if missing:
        print("missing Wayland helpers:", ", ".join(missing))
    else:
        print("all Wayland helpers present.")


if __name__ == "__main__":
    main()
