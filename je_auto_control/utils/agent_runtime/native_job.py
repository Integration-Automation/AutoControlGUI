"""Own a Windows helper process tree through a kill-on-close Job Object."""
from __future__ import annotations

import ctypes
import sys
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


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

    def close(self) -> None:
        """Closing the sole handle terminates only this owned process tree."""
        if self._handle:
            handle, self._handle = self._handle, None
            if not self._kernel.CloseHandle(handle):
                raise AgentTaskError("native helper job could not retire")
