"""Owned Win32 presence-only hooks; no key values, coordinates or input contents are retained."""
from __future__ import annotations

import ctypes
import sys
import threading
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.activity import ActivityGate, physical_event
from je_auto_control.utils.agent_runtime.errors import AgentTaskError


def _interactive() -> bool:
    if sys.platform != "win32":
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.OpenInputDesktop.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    user32.OpenInputDesktop.restype = ctypes.c_void_p
    user32.CloseDesktop.argtypes = (ctypes.c_void_p,)
    user32.GetUserObjectInformationW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32))
    handle = user32.OpenInputDesktop(0, False, 1)
    if not handle:
        return False
    try:
        name, needed = ctypes.create_unicode_buffer(256), ctypes.c_uint32()
        return bool(user32.GetUserObjectInformationW(handle, 2, name, ctypes.sizeof(name), ctypes.byref(needed))
                    and name.value.casefold() == "default")
    finally:
        user32.CloseDesktop(handle)


def _idle() -> float:
    if sys.platform != "win32":
        raise AgentTaskError("Win32 physical activity probe is unavailable")
    from je_auto_control.utils.idle_keepawake import idle_seconds
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    user32.GetAsyncKeyState.restype = ctypes.c_short
    if any(user32.GetAsyncKeyState(key) & 0x8000 for key in range(1, 255)):
        return 0
    return idle_seconds()


def _listener(callback: Callable[[], None]) -> Any:
    if sys.platform != "win32":
        raise AgentTaskError("Win32 physical activity listener is unavailable")
    from je_auto_control.windows.record.win32_input_hook import (
        Win32InputHook, _KBDLLHOOKSTRUCT, _MSLLHOOKSTRUCT,
    )

    class PresenceHook(Win32InputHook):
        """Keep only presence metadata and own the hook thread through retirement."""

        def start(self) -> None:
            self._thread = threading.Thread(target=self._run, name="AgentPresence", daemon=True)
            self._thread.start()
            if not self._ready.wait(5) or self.error or not self._thread.is_alive():
                raise AgentTaskError("physical activity hooks did not become ready")

        def alive(self) -> bool:
            return self._thread.is_alive() and not self.error

        def stop(self) -> list:
            super().stop()
            self._thread.join(timeout=1)
            if self._thread.is_alive():
                raise AgentTaskError("physical activity hooks have not retired")
            return []

        def _keyboard_proc(self, user32: Any) -> Any:
            return self._presence_proc(user32, "keyboard", _KBDLLHOOKSTRUCT)

        def _mouse_proc(self, user32: Any) -> Any:
            return self._presence_proc(user32, "mouse", _MSLLHOOKSTRUCT)

        def _presence_proc(self, user32: Any, kind: str, structure: Any) -> Any:
            def observe(code: int, message: int, pointer: int) -> Any:
                try:
                    if code >= 0:
                        data = ctypes.cast(pointer, ctypes.POINTER(structure)).contents
                        if physical_event(kind, int(data.flags)):
                            callback()
                except (OSError, ValueError, AttributeError):
                    self.error = "physical activity hook failed"
                    callback()
                return user32.CallNextHookEx(None, code, message, pointer)
            return observe

    return PresenceHook()


def windows_gate(takeover: Callable[[], None]) -> ActivityGate:
    """Construct an inert gate; hooks install only on explicit native target acquisition."""
    gate: ActivityGate | None = None

    def notify() -> None:
        if gate is not None:
            gate.notify()

    gate = ActivityGate(_listener(notify), _idle, _interactive, takeover)
    return gate
