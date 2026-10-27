"""Secured local message pipes; blocking byte operations belong only inside owned helpers."""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import importlib
import sys
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.presence_security_windows import WindowsPresenceSecurity

_PTR, _U32 = ctypes.c_void_p, ctypes.c_uint32
_INVALID = _PTR(-1).value


@dataclass(frozen=True)
class _PipeAPI:
    kernel: Any
    async_api: Any
    connection: Any


def _error() -> int:
    if sys.platform != 'win32':
        raise AgentTaskError('Windows physical presence native errors are unavailable')
    return ctypes.get_last_error()


def _bind(kernel: Any) -> None:
    signatures = {
        'CreateNamedPipeW': ([ctypes.c_wchar_p, *[_U32] * 6, _PTR], _PTR),
        'CreateFileW': ([ctypes.c_wchar_p, _U32, _U32, _PTR, _U32, _U32, _PTR], _PTR),
        'SetNamedPipeHandleState': ([_PTR, *[ctypes.POINTER(_U32)] * 3], ctypes.c_int),
        'CloseHandle': ([_PTR], ctypes.c_int),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result


class PresenceBytePipe:
    """Expose bounded immutable bytes only; never expose pickle send/recv on the native connection."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def _open(self) -> Any:
        if self._connection is None:
            raise AgentTaskError('physical presence byte pipe has closed')
        return self._connection

    def fileno(self) -> int:
        """Supply only the actual owned pipe handle to native endpoint verification."""
        return self._open().fileno()

    def send_bytes(self, raw: bytes) -> None:
        """One message of at most4096bytes; this potentially blocking call requires an outer fence."""
        if not isinstance(raw, bytes) or len(raw) > 4096:
            raise AgentTaskError('physical presence byte message exceeds its closed bound')
        self._open().send_bytes(raw)

    def recv_bytes(self, maximum: int = 4096) -> bytes:
        """Receive under the fixed bound, inside an owned helper with an external deadline."""
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum != 4096:
            raise AgentTaskError('physical presence byte receive bound must be4096')
        return self._open().recv_bytes(4096)

    def close(self) -> None:
        """Retire only this transferred connection; retain it if native close fails."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None


class WindowsPresencePipe:
    """Lazy actual native factory; trusted namespace/libraries are host test seams, never task fields."""

    def __init__(self, security: WindowsPresenceSecurity | None = None, namespace: str | None = None,
                 libraries: tuple[Any, Any, Any] | None = None) -> None:
        self._security = security if security is not None else WindowsPresenceSecurity()
        self._namespace, self._libraries = namespace, libraries
        self._native: Any = None
        self._name: str | None = None
        self._pending: set[int] = set()

    def _load(self) -> None:
        if self._native is not None:
            return
        if self._libraries is None:
            if sys.platform != 'win32':
                raise AgentTaskError('Windows physical presence pipes are unavailable')
            self._libraries = (
                ctypes.WinDLL('kernel32', use_last_error=True), importlib.import_module('_winapi'),
                importlib.import_module('multiprocessing.connection').PipeConnection)
        native = _PipeAPI(*self._libraries)
        _bind(native.kernel)
        self._name = self._security.name(self._namespace)
        self._native = native

    def _retain(self, handle: int, first: bool = False) -> int:
        if handle in (None, 0, _INVALID):
            if first and _error() == 5:
                raise AgentControlBusy('physical presence first pipe instance is not owned')
            raise AgentTaskError('physical presence native pipe is unavailable')
        self._pending.add(handle)
        return handle

    def create_instance(self, first: bool) -> int:
        """Create one descriptor-protected instance for this factory's internal listener."""
        flags = 0x40000003 | (0x80000 if first else 0)
        with self._security.attributes() as attributes:
            handle = self._native.kernel.CreateNamedPipeW(
                self._name, flags, 14, 17, 4096, 4096, 0, attributes.pointer())
            return self._retain(handle, first)

    def retire(self, handle: int) -> None:
        """Retire only a native handle still recorded as owned and not transferred."""
        if handle not in self._pending or not self._native.kernel.CloseHandle(handle):
            raise AgentTaskError('physical presence native pipe handle has not retired')
        self._pending.remove(handle)

    def connected(self, handle: int) -> PresenceBytePipe:
        """Transfer one actually connected instance to a byte-only connection owner."""
        self._owned(handle)
        result = PresenceBytePipe(self._native.connection(handle))
        self._pending.remove(handle)
        return result

    def wait_connected(self, handle: int) -> None:
        """Wait only inside an owned helper; its outer process deadline fences a blocked accept."""
        self._owned(handle)
        operation = self._native.async_api.ConnectNamedPipe(handle, overlapped=True)
        try:
            _count, error = operation.GetOverlappedResult(True)
        except BaseException:
            operation.cancel()
            raise
        if error:
            raise AgentTaskError('physical presence native pipe accept failed')

    def _owned(self, handle: int) -> None:
        if handle not in self._pending:
            raise AgentTaskError('physical presence native pipe handle is not owned')

    def listen(self) -> PresencePipeListener:
        """Reserve first-instance ownership before starting any physical observation source."""
        self._load()
        return PresencePipeListener(self, self.create_instance(True))

    def connect(self) -> PresenceBytePipe:
        """Open once, with identification-only QoS; never retry, impersonate or select another endpoint."""
        connection = self.connect_if_present()
        if connection is None:
            raise AgentTaskError('physical presence endpoint does not exist')
        return connection

    def connect_if_present(self) -> PresenceBytePipe | None:
        """Report absence only for native ERROR_FILE_NOT_FOUND; other failures never launch a source."""
        self._load()
        handle = self._native.kernel.CreateFileW(self._name, 0xC0000000, 0, None, 3, 0x40110000, None)
        if handle in (None, 0, _INVALID):
            error = _error()
            if error == 2:
                return None
            if error == 231:
                raise AgentControlBusy('physical presence connection capacity is busy')
            raise AgentTaskError('physical presence native pipe connection is unavailable')
        self._retain(handle)
        try:
            mode = _U32(2)
            if not self._native.kernel.SetNamedPipeHandleState(handle, ctypes.byref(mode), None, None):
                raise AgentTaskError('physical presence pipe message mode is unavailable')
            return self.connected(handle)
        except BaseException:
            self.retire(handle)
            raise


class PresencePipeListener:
    """Retain one pending instance across accepts; accepted byte pipes own their own handles."""

    def __init__(self, factory: WindowsPresencePipe, first: int) -> None:
        self._factory = factory
        self._pending = [first]
        self._closed = False

    def accept(self) -> PresenceBytePipe:
        """Serial owned-helper accept; reserve a successor before this potentially blocking wait."""
        if self._closed:
            raise AgentTaskError('physical presence pipe listener has closed')
        self._pending.append(self._factory.create_instance(False))
        handle = self._pending[0]
        try:
            self._factory.wait_connected(handle)
            connection = self._factory.connected(handle)
        except BaseException:
            self._factory.retire(handle)
            self._pending.remove(handle)
            raise
        self._pending.remove(handle)
        return connection

    def close(self) -> None:
        """Close only pending owned instances; never close a transferred client connection."""
        self._closed = True
        for handle in tuple(self._pending):
            self._factory.retire(handle)
            self._pending.remove(handle)
