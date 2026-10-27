"""Header-only Raw Input observation for the dedicated presence helper, never GUI input injection."""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
import math
import sys
import threading
from typing import Any, Callable
import uuid

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.activity_windows import _interactive
from je_auto_control.utils.agent_runtime.presence_native_types import NativeLayout as _Layout

_U32, _PTR = ctypes.c_uint32, ctypes.c_void_p


class _RawDevice(_Layout):
    _fields_ = [('usUsagePage', ctypes.c_uint16), ('usUsage', ctypes.c_uint16),
                ('dwFlags', _U32), ('hwndTarget', _PTR)]


class _RawHeader(_Layout):
    _fields_ = [('dwType', _U32), ('dwSize', _U32), ('hDevice', _PTR), ('wParam', ctypes.c_size_t)]


class _Point(_Layout):
    _fields_ = [('x', ctypes.c_int32), ('y', ctypes.c_int32)]


class _Message(_Layout):
    _fields_ = [('hwnd', _PTR), ('message', _U32), ('wParam', ctypes.c_size_t),
                ('lParam', ctypes.c_ssize_t), ('time', _U32), ('pt', _Point), ('lPrivate', _U32)]


class _WindowClass(_Layout):
    _fields_ = [('style', _U32), ('lpfnWndProc', _PTR), ('cbClsExtra', ctypes.c_int32),
                ('cbWndExtra', ctypes.c_int32), ('hInstance', _PTR), ('hIcon', _PTR), ('hCursor', _PTR),
                ('hbrBackground', _PTR), ('lpszMenuName', ctypes.c_wchar_p), ('lpszClassName', ctypes.c_wchar_p)]


def _bind(user: Any, kernel: Any) -> None:
    signatures = {
        'RegisterClassW': ([ctypes.POINTER(_WindowClass)], ctypes.c_uint16),
        'CreateWindowExW': ([_U32, ctypes.c_wchar_p, ctypes.c_wchar_p, _U32,
                            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, _PTR, _PTR, _PTR, _PTR], _PTR),
        'DefWindowProcW': ([_PTR, _U32, ctypes.c_size_t, ctypes.c_ssize_t], ctypes.c_ssize_t),
        'DestroyWindow': ([_PTR], ctypes.c_int),
        'UnregisterClassW': ([ctypes.c_wchar_p, _PTR], ctypes.c_int),
        'RegisterRawInputDevices': ([ctypes.POINTER(_RawDevice), _U32, _U32], ctypes.c_int),
        'GetRegisteredRawInputDevices': ([ctypes.POINTER(_RawDevice), ctypes.POINTER(_U32), _U32], _U32),
        'GetRawInputData': ([_PTR, _U32, _PTR, ctypes.POINTER(_U32), _U32], _U32),
        'MsgWaitForMultipleObjectsEx': ([_U32, ctypes.POINTER(_PTR), _U32, _U32, _U32], _U32),
        'PeekMessageW': ([ctypes.POINTER(_Message), _PTR, _U32, _U32, _U32], ctypes.c_int),
        'DispatchMessageW': ([ctypes.POINTER(_Message)], ctypes.c_ssize_t),
        'GetAsyncKeyState': ([ctypes.c_int], ctypes.c_short),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(user, name)
        function.argtypes, function.restype = arguments, result
    kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel.GetModuleHandleW.restype = _PTR


@dataclass
class _NativeWindow:
    callback: Any = field(default=None, init=False)
    physical: Callable[[], None] | None = field(default=None, init=False)
    window: int | None = field(default=None, init=False)
    instance: int | None = field(default=None, init=False)
    thread: int | None = field(default=None, init=False)
    name: str = field(default_factory=lambda: 'JEAgentPresence_' + uuid.uuid4().hex, init=False)
    registered: bool = field(default=False, init=False)


class Win32PresenceAPI:
    """Own only an invisible message window and its three raw registrations on one helper thread."""

    def __init__(self, libraries: tuple[Any, Any] | None = None,
                 interactive: Callable[[], bool] = _interactive) -> None:
        self._libraries = libraries
        self._interactive = interactive
        self._user: Any = None
        self._kernel: Any = None
        self._resources = _NativeWindow()
        self._callback_failed = self._closed = False

    @property
    def _callback(self) -> Any:
        return self._resources.callback

    def _load(self) -> None:
        if self._libraries is None:
            if sys.platform != 'win32':
                raise AgentTaskError('Windows physical presence requires a Win32 helper')
            self._libraries = (ctypes.WinDLL('user32', use_last_error=True),
                               ctypes.WinDLL('kernel32', use_last_error=True))
        self._user, self._kernel = self._libraries
        _bind(self._user, self._kernel)

    def _owner(self) -> None:
        if self._resources.thread is not None and self._resources.thread != threading.get_ident():
            raise AgentTaskError('physical presence window belongs to a different thread')

    def open(self, physical: Callable[[], None]) -> None:
        """Create the helper's message-only window and background header-only registrations."""
        if self._resources.thread is not None or self._closed:
            raise AgentTaskError('physical presence observer cannot restart')
        self._resources.thread, self._resources.physical = threading.get_ident(), physical
        try:
            self._load()
            prototype = getattr(ctypes, 'WINFUNCTYPE', ctypes.CFUNCTYPE)
            self._resources.callback = prototype(ctypes.c_ssize_t, _PTR, _U32, ctypes.c_size_t,
                                       ctypes.c_ssize_t)(self._window_proc)
            self._resources.instance = self._kernel.GetModuleHandleW(None)
            definition = _WindowClass(lpfnWndProc=ctypes.cast(self._callback, _PTR).value,
                                      hInstance=self._resources.instance, lpszClassName=self._resources.name)
            if not self._resources.instance or not self._user.RegisterClassW(definition.pointer()):
                raise AgentTaskError('physical presence window class could not start')
            self._resources.registered = True
            self._resources.window = self._user.CreateWindowExW(0, self._resources.name, '', 0, 0, 0, 0, 0,
                                                      _PTR(-3), None, self._resources.instance, None)
            if not self._resources.window:
                raise AgentTaskError('physical presence message window could not start')
            devices = (_RawDevice * 3)(*[_RawDevice(*row) for row in sorted(self._expected())])
            if not self._user.RegisterRawInputDevices(devices, 3, _RawDevice.size()):
                raise AgentTaskError('physical presence registration could not start')
        except (OSError, ValueError, TypeError, AttributeError, RuntimeError) as primary:
            try:
                self.close()
            except AgentTaskError as cleanup:
                raise primary from cleanup
            raise

    def _expected(self) -> set[tuple[int, int, int, int]]:
        window = self._resources.window or 0
        return {(1, 2, 0x100, window), (1, 6, 0x100, window), (0x0D, 0, 0x120, window)}

    def registrations(self) -> set[tuple[int, int, int, int]]:
        """Read actual process registrations; an inert/unstarted observer installs nothing."""
        self._owner()
        if not self._resources.window:
            return set()
        count = _U32()
        query = self._user.GetRegisteredRawInputDevices
        if query(None, ctypes.byref(count), _RawDevice.size()) == 0xFFFFFFFF or count.value > 16:
            raise AgentTaskError('physical presence registration query failed')
        if not count.value:
            return set()
        capacity = count.value
        devices = (_RawDevice * capacity)()
        if query(devices, ctypes.byref(count), _RawDevice.size()) != capacity:
            raise AgentTaskError('physical presence registration query changed')
        return {(row.usUsagePage, row.usUsage, row.dwFlags, row.hwndTarget or 0) for row in devices}

    def _header(self, code: int, handle: int) -> None:
        header = _RawHeader()
        size = _U32(header.size())
        copied = self._user.GetRawInputData(handle, 0x10000005, header.pointer(),
                                            ctypes.byref(size), header.size())
        if (copied != header.size() or header.dwSize < header.size()
                or header.dwType not in (0, 1, 2) or code not in (0, 1) or header.wParam != code):
            raise AgentTaskError('physical presence raw header is invalid')
        if self._resources.physical is None:
            raise AgentTaskError('physical presence callback is unavailable')
        self._resources.physical()

    def _window_proc(self, window: int, message: int, code: int, handle: int) -> int:
        try:
            if message == 0x00FF:
                self._header(code, handle)
        except (OSError, ValueError, TypeError, AttributeError, RuntimeError, OverflowError):
            self._callback_failed = True
        try:
            return int(self._user.DefWindowProcW(window, message, code, handle))
        except (OSError, ValueError, TypeError, AttributeError, RuntimeError):
            self._callback_failed = True
            return 0

    def _pump(self) -> None:
        message = _Message()
        for _index in range(1024):
            if not self._user.PeekMessageW(message.pointer(), None, 0, 0, 1):
                return
            if message.message == 0x12:
                raise AgentTaskError('physical presence observer quit unexpectedly')
            self._user.DispatchMessageW(message.pointer())
            if self._callback_failed:
                raise AgentTaskError('physical presence raw callback failed')
        if self._user.PeekMessageW(message.pointer(), None, 0, 0, 0):
            raise AgentControlBusy('physical presence input queue is still active')

    def poll(self, timeout: float) -> tuple[bool, bool]:
        """Drain bounded messages and verify registration/interactive/held state before a fresh sample."""
        self._owner()
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not 0 <= timeout <= 0.05 or not math.isfinite(timeout)):
            raise AgentTaskError('physical presence poll deadline must be finite and at most fifty milliseconds')
        if not self._resources.window or self._callback_failed:
            raise AgentTaskError('physical presence observer is unavailable')
        result = self._user.MsgWaitForMultipleObjectsEx(0, None, math.ceil(timeout * 1000), 0x04FF, 4)
        if result not in (0, 258):
            raise AgentTaskError('physical presence native wait failed')
        self._pump()
        if self.registrations() != self._expected():
            raise AgentTaskError('physical presence registration changed')
        held = any(self._user.GetAsyncKeyState(code) & 0x8000 for code in range(1, 256))
        return self._interactive(), held

    def _owned_classes(self) -> set[tuple[int, int]]:
        classes = {(page, usage) for page, usage, _flags, _window in self._expected()}
        return {(page, usage) for page, usage, _flags, window in self.registrations()
                if window == self._resources.window and (page, usage) in classes}

    def _remove_registrations(self) -> None:
        owned = self._owned_classes()
        if owned:
            devices = (_RawDevice * len(owned))(*[_RawDevice(page, usage, 1, None) for page, usage in owned])
            if not self._user.RegisterRawInputDevices(devices, len(owned), _RawDevice.size()):
                raise AgentTaskError('physical presence registrations have not retired')
            if self._owned_classes():
                raise AgentTaskError('physical presence registrations have not confirmed retirement')

    def close(self) -> None:
        """Retire only owned registrations/window/class; keep callbacks until retirement is confirmed."""
        self._owner()
        failed = False
        if self._resources.window:
            try:
                self._remove_registrations()
            except (OSError, ValueError, TypeError, AttributeError, RuntimeError):
                failed = True
            if not self._user.DestroyWindow(self._resources.window):
                raise AgentTaskError('physical presence window has not retired')
            self._resources.window = None
        if self._resources.registered:
            if not self._user.UnregisterClassW(self._resources.name, self._resources.instance):
                raise AgentTaskError('physical presence window class has not retired')
            self._resources.registered = False
        self._resources.callback, self._resources.physical, self._resources.thread = None, None, None
        self._closed = True
        if failed:
            raise AgentTaskError('physical presence registrations did not confirm retirement')
