"""Read-only facts about a Windows or macOS session, for ``probe_capabilities``.

``capabilities`` used to answer ``available`` for every Windows capability and
``unknown`` for every macOS one without looking. This module looks -- and only
looks. Nothing here sends input, changes focus, shows a window, installs a
hook, registers a hotkey or asks the user for a permission:

Windows (``user32`` / ``kernel32`` / ``advapi32`` / ``gdi32`` queries)
    * the process's integrity level (its token is opened ``TOKEN_QUERY``);
    * its session id -- session 0 has no interactive desktop;
    * the name of the desktop that is receiving input -- ``Winlogon`` while
      the workstation is locked or a UAC / Ctrl+Alt+Del screen is up;
    * whether that desktop can be opened with ``DESKTOP_HOOKCONTROL``, which a
      low-level hook needs. No hook is installed;
    * whether one pixel can be copied off the screen (a 1x1 ``BitBlt`` into a
      memory bitmap that is then freed).

macOS (the *preflight* calls, never the *request* ones, which prompt)
    * ``AXIsProcessTrusted()`` -- Accessibility, needed to post events;
    * ``CGPreflightScreenCaptureAccess()`` -- Screen Recording;
    * ``CGPreflightListenEventAccess()`` -- Input Monitoring.

A fact that could not be read is ``None`` and is reported as ``unknown``,
never as a yes. The macOS half has not been run on a Mac by its author.

Pure ``ctypes`` / lazy ``pyobjc`` imports; imports no ``PySide6``.
"""
from __future__ import annotations

import importlib
import platform as _platform
import sys
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

_READ_ERRORS = (OSError, AttributeError, ValueError, TypeError, RuntimeError,
                ImportError)

_TOKEN_QUERY = 0x0008
_TOKEN_INTEGRITY_LEVEL = 25
_DESKTOP_READOBJECTS = 0x0001
_DESKTOP_HOOKCONTROL = 0x0008
_UOI_NAME = 2
_SRCCOPY = 0x00CC0020
#: Upper bounds of the mandatory-label RIDs, lowest first.
_INTEGRITY_LEVELS = ((0x1000, "untrusted"), (0x2000, "low"), (0x3000, "medium"),
                     (0x4000, "high"))
#: Desktops that hold input while the user's own desktop is not reachable.
SECURE_DESKTOPS = frozenset({"winlogon", "screen-saver"})


@dataclass(frozen=True)
class WindowsFacts:
    """What the read-only Windows queries returned; ``None`` = could not be read."""

    #: ``untrusted`` / ``low`` / ``medium`` / ``high`` / ``system``.
    integrity: Optional[str] = None
    session_id: Optional[int] = None
    #: Name of the desktop receiving input; ``""`` when it could not be opened.
    input_desktop: Optional[str] = None
    #: Whether the input desktop opens with ``DESKTOP_HOOKCONTROL``.
    hook_access: Optional[bool] = None
    #: Whether a 1x1 copy off the screen succeeded.
    capture_ok: Optional[bool] = None
    capture_error: str = ""

    @property
    def secure_desktop(self) -> Optional[bool]:
        """Whether the workstation is locked or showing a secure desktop."""
        if self.input_desktop is None:
            return None
        return self.input_desktop == "" or self.input_desktop.lower() in SECURE_DESKTOPS


@dataclass(frozen=True)
class MacFacts:
    """What the macOS preflight calls returned; ``None`` = could not be asked."""

    accessibility: Optional[bool] = None
    screen_recording: Optional[bool] = None
    input_monitoring: Optional[bool] = None


def _guarded(read: Callable[[], Any]) -> Any:
    """``read()``, or ``None`` when the query itself failed."""
    try:
        return read()
    except _READ_ERRORS:
        return None


def _integrity_name(rid: int) -> str:
    for limit, name in _INTEGRITY_LEVELS:
        if rid < limit:
            return name
    return "system"


def _win_integrity() -> Optional[str]:
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD)]
    advapi32.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
    advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    advapi32.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
            kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)):
        return None
    try:
        size = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, _TOKEN_INTEGRITY_LEVEL, None, 0, ctypes.byref(size))
        if size.value == 0:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(
                token, _TOKEN_INTEGRITY_LEVEL, buffer, size, ctypes.byref(size)):
            return None
        # TOKEN_MANDATORY_LABEL starts with the SID pointer.
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        count = advapi32.GetSidSubAuthorityCount(sid)[0]
        return _integrity_name(int(advapi32.GetSidSubAuthority(sid, count - 1)[0]))
    finally:
        kernel32.CloseHandle(token)


def _win_session_id() -> Optional[int]:
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
    session = wintypes.DWORD(0)
    if not kernel32.ProcessIdToSessionId(
            kernel32.GetCurrentProcessId(), ctypes.byref(session)):
        return None
    return int(session.value)


def _open_input_desktop(access: int) -> Tuple[Any, Any]:
    """``(user32, handle)`` for the desktop receiving input; the handle may be null."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
    user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    return user32, user32.OpenInputDesktop(0, False, access)


def _win_input_desktop() -> str:
    """The input desktop's name; ``""`` when this process may not open it."""
    import ctypes
    from ctypes import wintypes
    user32, handle = _open_input_desktop(_DESKTOP_READOBJECTS)
    if not handle:
        return ""
    try:
        user32.GetUserObjectInformationW.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD)]
        name = ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD(0)
        if not user32.GetUserObjectInformationW(
                handle, _UOI_NAME, name, ctypes.sizeof(name), ctypes.byref(needed)):
            return ""
        return str(name.value)
    finally:
        user32.CloseDesktop(handle)


def _win_hook_access() -> bool:
    user32, handle = _open_input_desktop(_DESKTOP_HOOKCONTROL)
    if not handle:
        return False
    user32.CloseDesktop(handle)
    return True


def _win_capture() -> Tuple[bool, str]:
    """Copy one pixel off the screen into a memory bitmap, then free everything."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
    handle = wintypes.HANDLE
    user32.GetDC.argtypes, user32.GetDC.restype = [handle], handle
    user32.ReleaseDC.argtypes = [handle, handle]
    gdi32.CreateCompatibleDC.argtypes, gdi32.CreateCompatibleDC.restype = [handle], handle
    gdi32.CreateCompatibleBitmap.argtypes = [handle, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = handle
    gdi32.SelectObject.argtypes, gdi32.SelectObject.restype = [handle, handle], handle
    gdi32.DeleteObject.argtypes, gdi32.DeleteDC.argtypes = [handle], [handle]
    gdi32.BitBlt.argtypes = [handle, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             handle, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    screen = user32.GetDC(None)
    if not screen:
        return False, "GetDC returned no screen device context"
    memory = bitmap = previous = None
    try:
        memory = gdi32.CreateCompatibleDC(screen)
        bitmap = gdi32.CreateCompatibleBitmap(screen, 1, 1)
        if not memory or not bitmap:
            return False, "could not create a memory bitmap"
        previous = gdi32.SelectObject(memory, bitmap)
        if gdi32.BitBlt(memory, 0, 0, 1, 1, screen, 0, 0, _SRCCOPY):
            return True, ""
        return False, f"BitBlt failed (error {ctypes.get_last_error()})"  # type: ignore[attr-defined,unused-ignore]
    finally:
        if memory and previous:
            gdi32.SelectObject(memory, previous)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory:
            gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)


def read_windows_facts() -> WindowsFacts:
    """Query the live Windows session; every field ``None`` anywhere else."""
    if sys.platform != "win32":
        return WindowsFacts()
    capture = _guarded(_win_capture)
    return WindowsFacts(
        integrity=_guarded(_win_integrity), session_id=_guarded(_win_session_id),
        input_desktop=_guarded(_win_input_desktop), hook_access=_guarded(_win_hook_access),
        capture_ok=None if capture is None else capture[0],
        capture_error="" if capture is None else capture[1])


def _mac_preflight(modules: Tuple[str, ...], name: str) -> Optional[bool]:
    """Call the no-argument preflight ``name`` from the first module that has it."""
    for module_name in modules:
        try:
            # nosemgrep  # reason: the module names are the constants this file passes, not input
            function = getattr(importlib.import_module(module_name), name, None)
        except _READ_ERRORS:
            continue
        if callable(function):
            answer = _guarded(function)
            return None if answer is None else bool(answer)
    return None


def read_mac_facts() -> MacFacts:
    """Ask macOS what this process is permitted, without prompting.

    Only preflight calls are made. ``None`` everywhere off macOS, and for any
    call ``pyobjc`` does not expose on this system.
    """
    if sys.platform != "darwin":
        return MacFacts()
    return MacFacts(
        accessibility=_mac_preflight(("ApplicationServices", "HIServices"),
                                     "AXIsProcessTrusted"),
        screen_recording=_mac_preflight(("Quartz",), "CGPreflightScreenCaptureAccess"),
        input_monitoring=_mac_preflight(("Quartz",), "CGPreflightListenEventAccess"))


def _distribution_version(name: str) -> str:
    from importlib import metadata
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return ""


def cheap_backend_version(backend: str) -> str:
    """What the serving backend can say about its version without running anything.

    ``win32`` -> ``Windows <build>``; ``quartz`` -> ``macOS <version>; pyobjc
    <version>``; ``x11`` -> ``python-xlib <version>``. ``""`` when it is not
    known: on Wayland the tools (ydotool, grim, the portal) only report a
    version when they are run, which a probe does not do; and always when the
    backend is not this machine's.
    """
    if backend == "win32" and sys.platform == "win32":
        return f"Windows {_platform.version()}"
    if backend == "quartz" and sys.platform == "darwin":
        pyobjc = _distribution_version("pyobjc-core")
        return f"macOS {_platform.mac_ver()[0]}" + (f"; pyobjc {pyobjc}" if pyobjc else "")
    if backend == "x11" and sys.platform.startswith(("linux", "freebsd")):
        xlib = _distribution_version("python-xlib")
        return f"python-xlib {xlib}" if xlib else ""
    return ""


__all__ = [
    "MacFacts", "SECURE_DESKTOPS", "WindowsFacts", "cheap_backend_version",
    "read_mac_facts", "read_windows_facts",
]
