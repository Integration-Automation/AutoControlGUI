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
