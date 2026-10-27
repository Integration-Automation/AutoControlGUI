"""Own a Windows helper process tree through a kill-on-close Job Object."""
from __future__ import annotations

import ctypes
import math
import sys
import time
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_native_types import NativeLayout


class _Accounting(NativeLayout):
    """Actual JOBOBJECT_BASIC_ACCOUNTING_INFORMATION layout, including the live process count."""
    _fields_ = [('user', ctypes.c_longlong), ('kernel', ctypes.c_longlong),
                ('period_user', ctypes.c_longlong), ('period_kernel', ctypes.c_longlong),
                ('faults', ctypes.c_uint32), ('total', ctypes.c_uint32),
                ('active', ctypes.c_uint32), ('terminated', ctypes.c_uint32)]


class _ProcessList(NativeLayout):
    """Bounded native Job member list; PID values select query-only handles, never termination."""
    _fields_ = [('assigned', ctypes.c_uint32), ('listed', ctypes.c_uint32),
                ('pids', ctypes.c_size_t * 4096)]


def _deadline(timeout: float) -> float:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise AgentTaskError('native retirement deadline must be numeric')
    if not 0 <= timeout <= 3 or not math.isfinite(timeout):
        raise AgentTaskError('native retirement deadline must be finite and between0and3')
    return time.monotonic() + timeout


def _kernel() -> Any:
    if sys.platform != "win32":
        raise AgentTaskError("Windows Job Objects are unavailable on this platform")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.SetInformationJobObject.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)
    kernel.SetInformationJobObject.restype = ctypes.c_int
    kernel.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    kernel.AssignProcessToJobObject.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel.CloseHandle.restype = ctypes.c_int
    kernel.TerminateJobObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel.TerminateJobObject.restype = ctypes.c_int
    kernel.QueryInformationJobObject.argtypes = (
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)
    kernel.QueryInformationJobObject.restype = ctypes.c_int
    kernel.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.IsProcessInJob.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int))
    kernel.IsProcessInJob.restype = ctypes.c_int
    kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    return kernel


def _limits() -> Any:
    class BasicLimits(ctypes.Structure):
        """Native JOBOBJECT_BASIC_LIMIT_INFORMATION layout."""
        _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                    ("flags", ctypes.c_uint32), ("min_working", ctypes.c_size_t),
                    ("max_working", ctypes.c_size_t), ("active", ctypes.c_uint32),
                    ("affinity", ctypes.c_size_t), ("priority", ctypes.c_uint32), ("scheduling", ctypes.c_uint32)]

    class ExtendedLimits(ctypes.Structure):
        """Native extended limits, including the reserved IO_COUNTERS field."""
        _fields_ = [("basic", BasicLimits), ("io", ctypes.c_ulonglong * 6),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

    information = ExtendedLimits()
    information.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
    return information


class NativeJob:
    """A helper starts idle and receives no operation until its process tree is owned."""

    def __init__(self, process: Any) -> None:
        self._kernel = _kernel()
        self._process_refs: dict[int, int] = {}
        self._handle = self._kernel.CreateJobObjectW(None, None)
        if not self._handle:
            raise AgentTaskError("cannot create an owned native helper job")
        try:
            information = _limits()
            if not self._kernel.SetInformationJobObject(self._handle, 9, ctypes.byref(information),
                                                        ctypes.sizeof(information)):
                raise AgentTaskError("cannot configure native helper containment")
            if not self._kernel.AssignProcessToJobObject(self._handle, int(process._handle)):
                raise AgentTaskError("cannot attach native helper containment")
        except BaseException:  # reason: a partial constructor owns and must retire its new job handle
            self.close()
            raise

    def close(self, *, timeout: float = 3) -> None:
        """Confirm the actual owned tree is empty before closing its sole Job handle."""
        if self._handle:
            deadline = _deadline(timeout)
            try:
                self._capture_members(deadline)
            finally:
                if not self._kernel.TerminateJobObject(self._handle, 1):
                    raise AgentTaskError('cannot terminate the owned native helper tree')
            self._wait_empty(deadline)
            self._wait_members(deadline)
            self._close_members()
            if not self._kernel.CloseHandle(self._handle):
                raise AgentTaskError("native helper job could not retire")
            self._handle = None

    def _wait_empty(self, deadline: float) -> None:
        accounting = _Accounting()
        while True:
            if not self._kernel.QueryInformationJobObject(
                    self._handle, 1, accounting.pointer(), accounting.size(), None):
                raise AgentTaskError('native helper tree retirement is unknown')
            if accounting.active == 0:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AgentTaskError('native helper tree has not retired')
            time.sleep(min(0.01, remaining))

    def _capture_members(self, deadline: float) -> None:
        self._before(deadline)
        members = _ProcessList()
        if not self._kernel.QueryInformationJobObject(self._handle, 3, members.pointer(), members.size(), None):
            raise AgentTaskError('native helper tree members are unknown')
        if members.assigned != members.listed or members.listed > 4096:
            raise AgentTaskError('native helper tree member list is incomplete')
        for pid in members.pids[:members.listed]:
            self._before(deadline)
            if pid not in self._process_refs:
                self._capture_member(pid)

    def _before(self, deadline: float) -> None:
        if time.monotonic() >= deadline:
            raise AgentTaskError('native helper tree retirement deadline exhausted')

    def _capture_member(self, pid: int) -> None:
        if not 0 < pid <= (1 << 32) - 1:
            raise AgentTaskError('native helper tree member identity is invalid')
        handle = self._kernel.OpenProcess(0x101000, False, pid)
        if not handle:
            if sys.platform == 'win32' and ctypes.get_last_error() == 87:
                return
            raise AgentTaskError('native helper tree member object is unavailable')
        self._process_refs[pid] = handle
        belongs = ctypes.c_int()
        if not self._kernel.IsProcessInJob(handle, self._handle, ctypes.byref(belongs)) or not belongs.value:
            self._close_members()
            raise AgentTaskError('native helper process object is not an owned Job member')

    def _wait_members(self, deadline: float) -> None:
        for handle in self._process_refs.values():
            milliseconds = max(0, int((deadline - time.monotonic()) * 1000))
            if self._kernel.WaitForSingleObject(handle, milliseconds) != 0:
                raise AgentTaskError('native helper process object has not retired')

    def _close_members(self) -> None:
        for pid, handle in tuple(self._process_refs.items()):
            if not self._kernel.CloseHandle(handle):
                raise AgentTaskError('native helper process query handle has not retired')
            del self._process_refs[pid]
