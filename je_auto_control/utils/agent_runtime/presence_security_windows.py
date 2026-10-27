"""Query-only connected-process identity and current-user/System pipe security; no input APIs."""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from dataclasses import dataclass
from hashlib import sha256
import re
import sys
from typing import Any, Iterator

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_frames import identifier, unsigned
from je_auto_control.utils.agent_runtime.presence_native_types import NativeLayout

_PTR, _U32 = ctypes.c_void_p, ctypes.c_uint32


class _FileTime(NativeLayout):
    _fields_ = [('low', _U32), ('high', _U32)]


class _TokenUser(NativeLayout):
    _fields_ = [('sid', _PTR), ('attributes', _U32)]


class _SecurityAttributes(NativeLayout):
    _fields_ = [('length', _U32), ('descriptor', _PTR), ('inherit', ctypes.c_int)]


@dataclass(frozen=True)
class ProcessIdentity:
    """Native process metadata retained privately for a live pipe challenge, never PID authority."""

    pid: int
    sid: str
    session: int
    birth: int


def _bind(kernel: Any, advapi: Any) -> None:
    kernel_signatures = {
        'GetCurrentProcessId': ([], _U32),
        'OpenProcess': ([_U32, ctypes.c_int, _U32], _PTR),
        'CloseHandle': ([_PTR], ctypes.c_int),
        'ProcessIdToSessionId': ([_U32, ctypes.POINTER(_U32)], ctypes.c_int),
        'GetProcessTimes': ([_PTR, *[ctypes.POINTER(_FileTime)] * 4], ctypes.c_int),
        'GetNamedPipeServerProcessId': ([_PTR, ctypes.POINTER(_U32)], ctypes.c_int),
        'GetNamedPipeClientProcessId': ([_PTR, ctypes.POINTER(_U32)], ctypes.c_int),
        'WaitForSingleObject': ([_PTR, _U32], _U32),
        'LocalFree': ([_PTR], _PTR),
    }
    security_signatures = {
        'OpenProcessToken': ([_PTR, _U32, ctypes.POINTER(_PTR)], ctypes.c_int),
        'GetTokenInformation': ([_PTR, _U32, _PTR, _U32, ctypes.POINTER(_U32)], ctypes.c_int),
        'IsValidSid': ([_PTR], ctypes.c_int),
        'ConvertSidToStringSidW': ([_PTR, ctypes.POINTER(_PTR)], ctypes.c_int),
        'ConvertStringSecurityDescriptorToSecurityDescriptorW': (
            [ctypes.c_wchar_p, _U32, ctypes.POINTER(_PTR), ctypes.POINTER(_U32)], ctypes.c_int),
    }
    for library, signatures in ((kernel, kernel_signatures), (advapi, security_signatures)):
        for name, (arguments, result) in signatures.items():
            function = getattr(library, name)
            function.argtypes, function.restype = arguments, result


class PeerProcess:
    """Retain only query/synchronize rights to the actual connected endpoint process."""

    def __init__(self, kernel: Any, handle: int, identity: ProcessIdentity) -> None:
        self._kernel = kernel
        self._handle: int | None = handle
        self.identity = identity

    def alive(self) -> bool:
        """Check this actual process object without waiting, signalling or selecting another PID."""
        if self._handle is None:
            return False
        result = self._kernel.WaitForSingleObject(self._handle, 0)
        if result not in (0, 258):
            raise AgentTaskError('physical presence peer liveness is unavailable')
        return result == 258

    def close(self) -> None:
        """Close only the owned query handle; never terminate the process."""
        if self._handle is not None:
            if not self._kernel.CloseHandle(self._handle):
                raise AgentTaskError('physical presence peer handle has not retired')
            self._handle = None


class WindowsPresenceSecurity:
    """Derive endpoint/security from actual native user/session metadata, without native observation."""

    def __init__(self, libraries: tuple[Any, Any] | None = None) -> None:
        self._libraries = libraries
        self._kernel: Any = None
        self._advapi: Any = None

    def _load(self) -> None:
        if self._kernel is not None:
            return
        if self._libraries is None:
            if sys.platform != 'win32':
                raise AgentTaskError('Windows physical presence pipe security is unavailable')
            self._libraries = (ctypes.WinDLL('kernel32', use_last_error=True),
                               ctypes.WinDLL('advapi32', use_last_error=True))
        self._kernel, self._advapi = self._libraries
        _bind(self._kernel, self._advapi)

    def _close(self, handle: int) -> None:
        if not self._kernel.CloseHandle(handle):
            raise AgentTaskError('physical presence identity handle has not retired')

    def _sid_text(self, sid: int) -> str:
        pointer = _PTR()
        try:
            if not self._advapi.IsValidSid(sid) or not self._advapi.ConvertSidToStringSidW(sid, ctypes.byref(pointer)):
                raise AgentTaskError('physical presence native SID is unavailable')
            if not pointer.value:
                raise AgentTaskError('physical presence native SID is empty')
            text = ctypes.wstring_at(pointer.value)
            if len(text) > 192 or not re.fullmatch(r'S-1-(?:[0-9]+-)*[0-9]+', text):
                raise AgentTaskError('physical presence native SID is invalid')
            return text
        finally:
            if pointer.value and self._kernel.LocalFree(pointer):
                raise AgentTaskError('physical presence SID memory has not retired')

    def _sid(self, process: int) -> str:
        token = _PTR()
        if not self._advapi.OpenProcessToken(process, 8, ctypes.byref(token)) or not token.value:
            raise AgentTaskError('physical presence process token is unavailable')
        try:
            needed = _U32()
            self._advapi.GetTokenInformation(token.value, 1, None, 0, ctypes.byref(needed))
            if not _TokenUser.size() <= needed.value <= 65536:
                raise AgentTaskError('physical presence process token size is invalid')
            buffer = ctypes.create_string_buffer(needed.value)
            if not self._advapi.GetTokenInformation(token.value, 1, buffer, len(buffer), ctypes.byref(needed)):
                raise AgentTaskError('physical presence process token query failed')
            user = _TokenUser.from_buffer(buffer)
            if not user.sid:
                raise AgentTaskError('physical presence process token has no user')
            return self._sid_text(user.sid)
        finally:
            self._close(token.value)

    def _open(self, pid: int) -> PeerProcess:
        unsigned(pid, (1 << 32) - 1, 1)
        handle = self._kernel.OpenProcess(0x101000, False, pid)
        if not handle:
            raise AgentTaskError('physical presence process identity is unavailable')
        retained = False
        try:
            session = _U32()
            times = [_FileTime() for _index in range(4)]
            if not self._kernel.ProcessIdToSessionId(pid, ctypes.byref(session)):
                raise AgentTaskError('physical presence process session is unavailable')
            if not self._kernel.GetProcessTimes(handle, *[item.pointer() for item in times]):
                raise AgentTaskError('physical presence process creation time is unavailable')
            birth = unsigned((times[0].high << 32) | times[0].low, (1 << 64) - 1, 1)
            result = PeerProcess(self._kernel, handle, ProcessIdentity(pid, self._sid(handle), session.value, birth))
            retained = True
            return result
        finally:
            if not retained:
                self._close(handle)

    def current(self) -> ProcessIdentity:
        """Read the actual process token/session/creation time and release every temporary handle."""
        self._load()
        peer = self._open(self._kernel.GetCurrentProcessId())
        try:
            return peer.identity
        finally:
            peer.close()

    def peer(self, pipe: int, *, server: bool) -> PeerProcess:
        """Verify a pipe's actual endpoint user/session; the transport must still bind a fresh challenge."""
        if not isinstance(server, bool):
            raise AgentTaskError('physical presence pipe role is invalid')
        self._load()
        pid = _U32()
        getter = self._kernel.GetNamedPipeClientProcessId if server else self._kernel.GetNamedPipeServerProcessId
        if not getter(pipe, ctypes.byref(pid)):
            raise AgentTaskError('physical presence pipe endpoint is unavailable')
        peer = self._open(pid.value)
        accepted = False
        try:
            current = self.current()
            if peer.identity.sid != current.sid or peer.identity.session != current.session or not peer.alive():
                raise AgentTaskError('physical presence pipe peer is not the same live user/session')
            accepted = True
            return peer
        finally:
            if not accepted:
                peer.close()

    def name(self, namespace: str | None = None) -> str:
        """Choose a versioned endpoint from the actual SID/session; namespaces are trusted-host test seams."""
        value = self.current()
        digest = sha256(f'{value.sid}\0{value.session}'.encode('utf-8')).hexdigest()
        suffix = '-' + identifier(namespace) if namespace is not None else ''
        return '\\\\.\\pipe\\je-auto-presence-v1-' + digest + suffix

    @contextmanager
    def attributes(self) -> Iterator[_SecurityAttributes]:
        """Build a noninheritable descriptor granting only the current user and LocalSystem access."""
        sid = self.current().sid
        descriptor = _PTR()
        try:
            text = f'D:P(A;;GA;;;SY)(A;;GA;;;{sid})'
            convert = self._advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
            if not convert(text, 1, ctypes.byref(descriptor), None) or not descriptor.value:
                raise AgentTaskError('physical presence pipe security descriptor is unavailable')
            yield _SecurityAttributes(_SecurityAttributes.size(), descriptor.value, False)
        finally:
            if descriptor.value and self._kernel.LocalFree(descriptor):
                raise AgentTaskError('physical presence pipe security memory has not retired')
