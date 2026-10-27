"""Console/protocol session queries are exercised only against fake DLLs, never the live desktop."""
import ctypes
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from .test_agent_presence_win32 import Function, observer


class Native:
    def __init__(self):
        self.session = self.console = 7
        self.protocol = self.remote = self.state = self.metric_remote = self.metric_shadow = 0
        self.pid_ok, self.query_failure, self.bad_size, self.null = True, None, None, False
        self.buffers, self.freed = {}, []
        self.kernel = SimpleNamespace(GetCurrentProcessId=Function(lambda: 42),
            ProcessIdToSessionId=Function(self.current), WTSGetActiveConsoleSessionId=Function(lambda: self.console))
        self.user = SimpleNamespace(GetSystemMetrics=Function(self.metric))
        self.wts = SimpleNamespace(WTSQuerySessionInformationW=Function(self.query), WTSFreeMemory=Function(self.free))

    def current(self, pid, session):
        assert pid == 42
        ctypes.cast(session, ctypes.POINTER(ctypes.c_uint32)).contents.value = self.session
        return self.pid_ok

    def metric(self, code):
        assert code in (0x1000, 0x2001)
        return self.metric_remote if code == 0x1000 else self.metric_shadow

    def query(self, server, session, info, pointer, count):
        assert server is None and session == 0xFFFFFFFF
        value = ctypes.c_uint16(self.protocol) if info == 16 else ctypes.c_int32(
            self.remote if info == 29 else self.state)
        assert info in (16, 29, 8)
        address = ctypes.addressof(value)
        self.buffers[address] = value
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p)).contents.value = None if self.null else address
        ctypes.cast(count, ctypes.POINTER(ctypes.c_uint32)).contents.value = (
            self.bad_size if self.bad_size is not None else ctypes.sizeof(value))
        return info != self.query_failure

    def free(self, address):
        self.freed.append(address.value if hasattr(address, 'value') else address)


def console(native):
    from je_auto_control.utils.agent_runtime.presence_session_windows import WindowsConsoleSession
    return WindowsConsoleSession(libraries=(native.user, native.kernel, native.wts))


def test_console_guard_construction_is_inert_and_all_checks_use_current_local_session_queries():
    native = Native()
    guard = console(native)
    assert not native.kernel.GetCurrentProcessId.calls and not native.freed
    guard.check()
    guard.check()
    assert [row[2] for row in native.wts.WTSQuerySessionInformationW.calls] == [16, 29, 8] * 2
    assert len(native.freed) == 6
    assert native.kernel.ProcessIdToSessionId.restype is ctypes.c_int
    assert native.wts.WTSQuerySessionInformationW.argtypes[-1] == ctypes.POINTER(ctypes.c_uint32)


@pytest.mark.parametrize('field,value', [('console', 0xFFFFFFFF), ('console', 0), ('session', 8), ('session', 0),
    ('pid_ok', False), ('protocol', 1), ('protocol', 2), ('protocol', 65535), ('remote', 1), ('remote', 2),
    ('remote', -1), ('state', 1), ('state', 4), ('state', 6), ('metric_remote', 1), ('metric_shadow', 1),
    ('query_failure', 16), ('query_failure', 29), ('query_failure', 8), ('bad_size', 1), ('bad_size', 1000),
    ('null', True)])
def test_remote_shadow_unknown_detaching_and_malformed_native_queries_refuse_permission(field, value):
    native = Native()
    setattr(native, field, value)
    with pytest.raises(AgentTaskError):
        console(native).check()
    if native.wts.WTSQuerySessionInformationW.calls and not native.null:
        assert native.freed


def test_console_guard_rechecks_session_change_instead_of_caching_initial_authorization():
    native = Native()
    guard = console(native)
    guard.check()
    native.remote = 1
    with pytest.raises(AgentTaskError):
        guard.check()
    assert len(native.wts.WTSQuerySessionInformationW.calls) == 5


def test_unsupported_platform_never_loads_dlls(monkeypatch):
    from je_auto_control.utils.agent_runtime import presence_session_windows
    monkeypatch.setattr(presence_session_windows, 'sys', SimpleNamespace(platform='linux'))
    with pytest.raises(AgentTaskError):
        presence_session_windows.WindowsConsoleSession().check()


def test_observer_refuses_session_before_creating_any_window_or_raw_registration(monkeypatch):
    api, native = observer(monkeypatch)

    def refuse():
        raise AgentTaskError('test unsupported console')

    api._support.session = refuse
    with pytest.raises(AgentTaskError, match='console'):
        api.open(lambda: None)
    assert not native.user.CreateWindowExW.calls and not native.user.RegisterClassW.calls


def test_observer_rechecks_supported_session_for_every_fresh_poll(monkeypatch):
    api, _native = observer(monkeypatch)
    calls = []
    api._support.session = lambda: calls.append('checked')
    try:
        api.open(lambda: None)
        api.poll(0)
        api.poll(0)
        assert len(calls) >= 3
    finally:
        api.close()
