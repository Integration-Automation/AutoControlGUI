"""Query-only current physical-console support checks; remote or unknown sessions fail closed."""
from __future__ import annotations

import ctypes
import sys
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError

_U32, _PTR = ctypes.c_uint32, ctypes.c_void_p


def _bind(user: Any, kernel: Any, wts: Any) -> None:
    signatures: tuple[tuple[Any, list[Any], Any], ...] = (
        (user.GetSystemMetrics, [ctypes.c_int], ctypes.c_int),
        (kernel.GetCurrentProcessId, [], _U32),
        (kernel.ProcessIdToSessionId, [_U32, ctypes.POINTER(_U32)], ctypes.c_int),
        (kernel.WTSGetActiveConsoleSessionId, [], _U32),
        (wts.WTSQuerySessionInformationW,
         [_PTR, _U32, ctypes.c_int, ctypes.POINTER(_PTR), ctypes.POINTER(_U32)], ctypes.c_int),
        (wts.WTSFreeMemory, [_PTR], None),
    )
    for function, arguments, result in signatures:
        function.argtypes, function.restype = arguments, result


class WindowsConsoleSession:
    """A helper-local DLL binding; every check queries the actual current session again."""

    def __init__(self, libraries: tuple[Any, Any, Any] | None = None) -> None:
        self._libraries = libraries
        self._native: tuple[Any, Any, Any] | None = None
        self._state = 'not_checked'

    def _load(self) -> tuple[Any, Any, Any]:
        if self._native is None:
            if self._libraries is None:
                if sys.platform != 'win32':
                    raise AgentTaskError('physical-console presence requires a Windows helper')
                self._libraries = (ctypes.WinDLL('user32', use_last_error=True),
                                   ctypes.WinDLL('kernel32', use_last_error=True),
                                   ctypes.WinDLL('wtsapi32', use_last_error=True))
            user, kernel, wts = self._libraries
            _bind(user, kernel, wts)
            self._native = user, kernel, wts
        return self._native

    @staticmethod
    def _query(wts: Any, info: int, layout: Any) -> int:
        buffer, size = _PTR(), _U32()
        try:
            success = wts.WTSQuerySessionInformationW(None, 0xFFFFFFFF, info,
                                                      ctypes.byref(buffer), ctypes.byref(size))
            if not success or not buffer.value or size.value != ctypes.sizeof(layout):
                raise AgentTaskError('physical-console session query is unavailable or malformed')
            return ctypes.cast(buffer, ctypes.POINTER(layout)).contents.value
        finally:
            if bool(buffer):
                wts.WTSFreeMemory(buffer)

    def check(self) -> None:
        """Require matching physical console, active local protocol and no remote/shadow indication."""
        try:
            user, kernel, wts = self._load()
            session = _U32()
            if not kernel.ProcessIdToSessionId(kernel.GetCurrentProcessId(), ctypes.byref(session)):
                raise AgentTaskError('physical-console process session is unknown')
            console = kernel.WTSGetActiveConsoleSessionId()
            if session.value == 0 or console in (0, 0xFFFFFFFF) or session.value != console:
                raise AgentTaskError('physical presence requires the attached local console session')
            if user.GetSystemMetrics(0x1000) or user.GetSystemMetrics(0x2001):
                raise AgentTaskError('remote or shadow desktop presence is unsupported')
            queries = ((16, ctypes.c_uint16), (29, ctypes.c_int32), (8, ctypes.c_int32))
            if any(self._query(wts, info, layout) != 0 for info, layout in queries):
                raise AgentTaskError('physical presence requires active nonremote console protocol')
            self._state = 'supported'
        except (OSError, ValueError, TypeError, AttributeError, RuntimeError) as error:
            self._state = 'unavailable'
            raise AgentTaskError('physical-console session support could not be established') from error

    def status(self) -> dict:
        """Report only the last coarse classification; passive metadata never authorizes input."""
        return {'state': self._state, 'native_evidence': 'not_recorded'}
