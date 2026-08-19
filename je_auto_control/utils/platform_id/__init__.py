"""Which operating-system family this is, asked once and spelled one way.

``sys.platform`` was compared against literal lists in over a hundred places,
and every one of those lists named ``win32``/``cygwin``/``msys``, ``darwin``,
``linux``/``linux2`` and nothing else. That is fine until an operating system
turns up that is none of them and still runs X11 — a FreeBSD, OpenBSD or
NetBSD desktop is an ordinary X11 desktop, and the X11 backend works there —
at which point every one of those lists is a separate place to be wrong.

The distinction that actually matters to this project is not "which kernel"
but **which input and display stack**, so that is what these answer.
"""
import sys

__all__ = [
    "BSD_PREFIXES", "current_family", "is_bsd", "is_macos", "is_windows",
    "is_x11_unix",
]

#: ``sys.platform`` on the BSDs carries the major version — ``freebsd14``,
#: ``openbsd7`` — so these are matched by prefix rather than by equality.
BSD_PREFIXES = ("freebsd", "openbsd", "netbsd", "dragonfly")


def is_windows(platform: str = "") -> bool:
    """Windows, including the POSIX emulation layers that ship the Win32 API."""
    return (platform or sys.platform) in ("win32", "cygwin", "msys")


def is_macos(platform: str = "") -> bool:
    """macOS, where the backend is Quartz rather than X11."""
    return (platform or sys.platform) == "darwin"


def is_bsd(platform: str = "") -> bool:
    """One of the BSDs, which run the same X11 stack as Linux."""
    return (platform or sys.platform).startswith(BSD_PREFIXES)


def is_x11_unix(platform: str = "") -> bool:
    """A Unix whose desktop is X11 (or Wayland with XWayland underneath).

    Linux and the BSDs both qualify. This is the test the X11 backend
    modules guard on: what they need is an X server and ``python-Xlib``,
    neither of which is Linux-specific.
    """
    name = platform or sys.platform
    return name.startswith("linux") or is_bsd(name)


def current_family(platform: str = "") -> str:
    """``windows`` / ``macos`` / ``linux`` / ``bsd`` / the raw name."""
    name = platform or sys.platform
    if is_windows(name):
        return "windows"
    if is_macos(name):
        return "macos"
    if name.startswith("linux"):
        return "linux"
    if is_bsd(name):
        return "bsd"
    return name
