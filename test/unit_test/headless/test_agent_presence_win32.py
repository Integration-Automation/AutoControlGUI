"""Real ctypes observer code is exercised only through fake DLLs and in-memory messages."""
from concurrent.futures import ThreadPoolExecutor
import ctypes
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError


class Function:
    def __init__(self, body):
        self.body = body
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.body(*args)


class FakeWindows:
    """Support only observation/resource APIs; no foreground/input API exists on these DLLs."""

    def __init__(self, module):
        self.module = module
        self.window = 0x100000001
        self.registrations = []
        self.messages = []
        self.header_type, self.header_device = 1, 17
        self.header_size, self.header_code = 64, 1
        self.header_result = ctypes.sizeof(module._RawHeader)
        self.wait_result = 258
        self.registration_ok = self.destroy_ok = True
        self.ignore_remove = False
        self.api = None
        self.user = SimpleNamespace(
            RegisterClassW=Function(lambda *_: 1),
            CreateWindowExW=Function(lambda *_: self.window),
            DefWindowProcW=Function(lambda *_: 0),
            DestroyWindow=Function(lambda *_: self.destroy_ok),
            UnregisterClassW=Function(lambda *_: 1),
            RegisterRawInputDevices=Function(self.register),
            GetRegisteredRawInputDevices=Function(self.registered),
            GetRawInputData=Function(self.header),
            MsgWaitForMultipleObjectsEx=Function(lambda *_: self.wait_result),
            PeekMessageW=Function(self.peek), DispatchMessageW=Function(self.dispatch),
            GetAsyncKeyState=Function(lambda *_: 0))
        self.kernel = SimpleNamespace(GetModuleHandleW=Function(lambda *_: 0x100000002))

    def register(self, devices, count, _size):
        if not self.registration_ok:
            return False
        for index in range(count):
            item = devices[index]
            if item.dwFlags == 1 and self.ignore_remove:
                continue
            key = (item.usUsagePage, item.usUsage)
            self.registrations = [row for row in self.registrations if row[:2] != key]
            if item.dwFlags != 1:
                self.registrations.append((*key, item.dwFlags, item.hwndTarget or 0))
        return True

    def registered(self, devices, count, _size):
        count_ptr = ctypes.cast(count, ctypes.POINTER(ctypes.c_uint32))
        if devices is None:
            count_ptr.contents.value = len(self.registrations)
            return 0
        for index, row in enumerate(self.registrations):
            devices[index] = self.module._RawDevice(*row)
        return len(self.registrations)

    def header(self, _handle, command, buffer, size, header_size):
        assert command == 0x10000005
        assert header_size == ctypes.sizeof(self.module._RawHeader)
        assert ctypes.cast(size, ctypes.POINTER(ctypes.c_uint32)).contents.value == header_size
        data = ctypes.cast(buffer, ctypes.POINTER(self.module._RawHeader)).contents
        data.dwType, data.dwSize = self.header_type, self.header_size
        data.hDevice, data.wParam = self.header_device, self.header_code
        return self.header_result

    def peek(self, pointer, _window, _low, _high, remove):
        if not self.messages:
            return False
        values = self.messages.pop(0) if remove else self.messages[0]
        message = ctypes.cast(pointer, ctypes.POINTER(self.module._Message)).contents
        message.hwnd = self.window
        message.message, message.wParam, message.lParam = values
        return True

    def dispatch(self, pointer):
        message = ctypes.cast(pointer, ctypes.POINTER(self.module._Message)).contents
        return self.api._callback(message.hwnd, message.message, message.wParam, message.lParam)


def observer(monkeypatch):
    from je_auto_control.utils.agent_runtime import presence_win32 as module
    fake = FakeWindows(module)
    api = module.Win32PresenceAPI((fake.user, fake.kernel), interactive=lambda: True)
    fake.api = api
    return api, fake


def test_construction_and_unstarted_inspection_make_no_dll_calls(monkeypatch):
    api, fake = observer(monkeypatch)
    assert api.registrations() == set()
    assert all(not value.calls for value in vars(fake.user).values())
    with pytest.raises(AgentTaskError):
        api.poll(0)
    api.close()
    assert all(not value.calls for value in vars(fake.user).values())


def test_message_only_window_and_background_registrations_preserve_native_pointer_width(monkeypatch):
    api, fake = observer(monkeypatch)
    try:
        api.open(lambda: None)
        create, = fake.user.CreateWindowExW.calls
        assert create[3] == 0
        assert create[8].value == ctypes.c_void_p(-3).value
        assert fake.user.CreateWindowExW.restype is ctypes.c_void_p
        assert api.registrations() == {(1, 2, 0x100, fake.window), (1, 6, 0x100, fake.window),
                                       (0x0D, 0, 0x120, fake.window)}
        assert api.poll(0) == (True, False)
    finally:
        api.close()
    assert fake.registrations == []
    assert fake.user.DestroyWindow.calls == [(fake.window,)]
    assert len(fake.user.UnregisterClassW.calls) == 1
    assert api._callback is None


@pytest.mark.parametrize('kind,device', [(0, 17), (1, 17), (2, 17), (0, 0)])
def test_raw_header_only_counts_devices_and_zero_handle_touchpad(monkeypatch, kind, device):
    api, fake = observer(monkeypatch)
    notices = []
    try:
        api.open(lambda: notices.append('presence'))
        fake.header_type, fake.header_device = kind, device
        fake.messages.append((0x00FF, 1, 99))
        assert api.poll(0) == (True, False)
        assert notices == ['presence']
        assert len(fake.user.GetRawInputData.calls) == 1
        assert len(fake.user.DefWindowProcW.calls) == 1
    finally:
        api.close()


def test_legacy_software_messages_are_not_physical_authority(monkeypatch):
    api, fake = observer(monkeypatch)
    notices = []
    try:
        api.open(lambda: notices.append(True))
        fake.messages.extend([(0x100, 0, 0), (0x200, 0, 0), (0x102, 0, 0)])
        api.poll(0)
        assert notices == []
        assert fake.user.GetRawInputData.calls == []
    finally:
        api.close()


@pytest.mark.parametrize('attribute,value', [('header_result', 0xFFFFFFFF), ('header_result', 8),
    ('header_type', 99), ('header_size', 1), ('header_code', 99)])
def test_invalid_header_fails_monitoring_without_retaining_payload(monkeypatch, attribute, value):
    api, fake = observer(monkeypatch)
    notices = []
    try:
        api.open(lambda: notices.append(True))
        setattr(fake, attribute, value)
        fake.messages.append((0x00FF, 1, 99))
        with pytest.raises(AgentTaskError):
            api.poll(0)
        assert notices == []
        assert len(fake.user.DefWindowProcW.calls) == 1
    finally:
        api.close()


def test_registration_replacement_refuses_quiet_sample_and_cleanup_preserves_foreign_window(monkeypatch):
    api, fake = observer(monkeypatch)
    api.open(lambda: None)
    fake.registrations[0] = (1, 2, 0x100, 555)
    with pytest.raises(AgentTaskError, match='registration'):
        api.poll(0)
    api.close()
    assert fake.registrations == [(1, 2, 0x100, 555)]


def test_failed_registration_retires_only_partial_owned_window_and_class(monkeypatch):
    api, fake = observer(monkeypatch)
    fake.registration_ok = False
    with pytest.raises(AgentTaskError):
        api.open(lambda: None)
    assert fake.user.DestroyWindow.calls == [(fake.window,)]
    assert len(fake.user.UnregisterClassW.calls) == 1
    assert api._callback is None


def test_native_wait_failure_cannot_report_a_healthy_source(monkeypatch):
    api, fake = observer(monkeypatch)
    try:
        api.open(lambda: None)
        fake.wait_result = 0xFFFFFFFF
        with pytest.raises(AgentTaskError):
            api.poll(0)
    finally:
        api.close()


def test_backlog_is_bounded_and_requires_a_fresh_successful_drain(monkeypatch):
    api, fake = observer(monkeypatch)
    try:
        api.open(lambda: None)
        fake.messages = [(0x100, 0, 0)] * 1025
        with pytest.raises(AgentControlBusy, match='queue'):
            api.poll(0)
        assert len(fake.messages) == 1
        assert api.poll(0) == (True, False)
    finally:
        api.close()


def test_poll_and_cleanup_cannot_run_on_a_different_window_owner_thread(monkeypatch):
    api, fake = observer(monkeypatch)
    try:
        api.open(lambda: None)
        with ThreadPoolExecutor(max_workers=1) as executor:
            for operation in (lambda: api.poll(0), api.close):
                with pytest.raises(AgentTaskError, match='thread'):
                    executor.submit(operation).result(timeout=1)
        assert fake.user.DestroyWindow.calls == []
    finally:
        api.close()


def test_failed_window_retirement_keeps_callback_and_class_alive(monkeypatch):
    api, fake = observer(monkeypatch)
    api.open(lambda: None)
    fake.destroy_ok = False
    with pytest.raises(AgentTaskError, match='retir'):
        api.close()
    assert api._callback is not None
    assert not fake.user.UnregisterClassW.calls
    fake.destroy_ok = True
    api.close()


def test_registration_remove_return_value_is_not_independent_retirement_evidence(monkeypatch):
    api, fake = observer(monkeypatch)
    api.open(lambda: None)
    fake.ignore_remove = True
    with pytest.raises(AgentTaskError, match='retir'):
        api.close()
    assert fake.user.DestroyWindow.calls == [(fake.window,)]


@pytest.mark.parametrize('timeout', [True, -1, float('nan'), float('inf'), 0.1])
def test_native_poll_never_accepts_an_unbounded_or_untyped_wait(monkeypatch, timeout):
    api, fake = observer(monkeypatch)
    try:
        api.open(lambda: None)
        with pytest.raises(AgentTaskError):
            api.poll(timeout)
        assert fake.user.MsgWaitForMultipleObjectsEx.calls == []
    finally:
        api.close()


def test_huge_integer_wait_is_rejected_as_a_typed_deadline_error(monkeypatch):
    api, fake = observer(monkeypatch)
    try:
        api.open(lambda: None)
        with pytest.raises(AgentTaskError):
            api.poll(10 ** 1000)
        assert fake.user.MsgWaitForMultipleObjectsEx.calls == []
    finally:
        api.close()
