"""Native pipe flags, descriptor lifetime and byte-only ownership without any desktop APIs."""
from contextlib import contextmanager
import ctypes
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError


class Function:
    def __init__(self, body):
        self.body, self.calls = body, []

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        return self.body(*args, **kwargs)


class Security:
    def __init__(self):
        self.active, self.names = False, []

    def name(self, namespace):
        self.names.append(namespace)
        return r'\\.\pipe\je-auto-presence-v1-test'

    @contextmanager
    def attributes(self):
        from je_auto_control.utils.agent_runtime.presence_security_windows import _SecurityAttributes
        self.active = True
        try:
            yield _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), 12345, False)
        finally:
            self.active = False


class Native:
    def __init__(self, security):
        self.security, self.handles, self.calls = security, set(), []
        self.error, self.fail_create, self.fail_state, self.fail_close = 0, False, False, False
        self.fail_wait, self.fail_wrap = False, False
        self.next_handle = 0x100000000
        self.kernel = SimpleNamespace(CreateNamedPipeW=Function(self.create), CreateFileW=Function(self.open),
            SetNamedPipeHandleState=Function(self.state), CloseHandle=Function(self.close))
        self.async_api = SimpleNamespace(ConnectNamedPipe=Function(self.connect))

    def allocate(self):
        self.next_handle += 1
        self.handles.add(self.next_handle)
        return self.next_handle

    def create(self, *args):
        from je_auto_control.utils.agent_runtime.presence_security_windows import _SecurityAttributes
        attributes = ctypes.cast(args[-1], ctypes.POINTER(_SecurityAttributes)).contents
        assert self.security.active and attributes.descriptor == 12345 and attributes.inherit == 0
        self.calls.append('create')
        return ctypes.c_void_p(-1).value if self.fail_create else self.allocate()

    def open(self, *_args):
        self.calls.append('open')
        return ctypes.c_void_p(-1).value if self.fail_create else self.allocate()

    def state(self, handle, mode, *_unused):
        assert handle in self.handles
        assert ctypes.cast(mode, ctypes.POINTER(ctypes.c_uint32)).contents.value == 2
        return not self.fail_state

    def close(self, handle):
        assert handle in self.handles
        if self.fail_close:
            return False
        self.handles.remove(handle)
        self.calls.append(('close', handle))
        return True

    def connect(self, handle, *, overlapped):
        assert handle in self.handles and overlapped is True
        self.calls.append(('accept', handle))

        def wait(block):
            assert block is True
            if self.fail_wait:
                raise OSError('owned test wait failure')
            return 0, 0

        return SimpleNamespace(GetOverlappedResult=wait, cancel=lambda: self.calls.append('cancel'))

    def wrap(self, handle):
        assert handle in self.handles
        if self.fail_wrap:
            raise OSError('owned test wrapper failure')
        self.calls.append(('wrap', handle))
        return SimpleNamespace(fileno=lambda: handle, send_bytes=lambda raw: self.calls.append(('send', raw)),
            recv_bytes=lambda maximum: b'x' * maximum, close=lambda: self.close(handle))


def factory(monkeypatch):
    from je_auto_control.utils.agent_runtime import presence_pipe_windows as module
    security = Security()
    native = Native(security)
    monkeypatch.setattr(module, '_error', lambda: native.error)
    api = module.WindowsPresencePipe(security=security, namespace='a' * 32,
                                     libraries=(native.kernel, native.async_api, native.wrap))
    return api, native, security


def test_constructor_is_inert_and_first_instance_uses_actual_noninheritable_descriptor(monkeypatch):
    api, native, security = factory(monkeypatch)
    assert not native.calls and not security.names
    listener = api.listen()
    try:
        args, = native.kernel.CreateNamedPipeW.calls
        assert args[0] == r'\\.\pipe\je-auto-presence-v1-test'
        assert args[1:7] == (0x40080003, 14, 17, 4096, 4096, 0)
        assert security.names == ['a' * 32] and not security.active
        assert native.kernel.CreateNamedPipeW.restype is ctypes.c_void_p
    finally:
        listener.close()
    assert not native.handles


def test_accept_reserves_next_instance_before_wait_and_transfers_only_connected_handle(monkeypatch):
    api, native, _ = factory(monkeypatch)
    listener = api.listen()
    connection = listener.accept()
    assert native.calls[:3] == ['create', 'create', ('accept', 0x100000001)]
    assert native.kernel.CreateNamedPipeW.calls[1][1] == 0x40000003
    assert connection.fileno() == 0x100000001 and len(native.handles) == 2
    listener.close()
    listener.close()
    assert native.handles == {0x100000001}
    connection.close()
    connection.close()
    assert not native.handles
    with pytest.raises(AgentTaskError):
        listener.accept()


def test_client_uses_identification_only_qos_overlapped_message_mode_and_no_retries(monkeypatch):
    api, native, security = factory(monkeypatch)
    connection = api.connect()
    try:
        args, = native.kernel.CreateFileW.calls
        assert args == (r'\\.\pipe\je-auto-presence-v1-test', 0xC0000000, 0, None, 3, 0x40110000, None)
        assert len(native.kernel.SetNamedPipeHandleState.calls) == 1
        assert security.names == ['a' * 32]
    finally:
        connection.close()
    assert not native.handles


def test_only_verified_missing_endpoint_may_be_reported_as_absent(monkeypatch):
    api, native, _security = factory(monkeypatch)
    native.fail_create, native.error = True, 2
    assert api.connect_if_present() is None
    assert len(native.kernel.CreateFileW.calls) == 1 and not native.handles


@pytest.mark.parametrize('error,kind', [(5, AgentTaskError), (231, AgentControlBusy), (53, AgentTaskError)])
def test_denied_busy_or_unknown_endpoint_is_never_reported_missing(monkeypatch, error, kind):
    api, native, _security = factory(monkeypatch)
    native.fail_create, native.error = True, error
    with pytest.raises(kind):
        api.connect_if_present()
    assert len(native.kernel.CreateFileW.calls) == 1 and not native.handles


@pytest.mark.parametrize('listen', [True, False])
def test_open_failure_never_wraps_or_borrows_a_foreign_handle(monkeypatch, listen):
    api, native, _ = factory(monkeypatch)
    native.fail_create = True
    native.error = 5
    with pytest.raises(AgentControlBusy if listen else AgentTaskError):
        api.listen() if listen else api.connect()
    assert len(native.kernel.CreateNamedPipeW.calls if listen else native.kernel.CreateFileW.calls) == 1
    assert not native.handles and not native.async_api.ConnectNamedPipe.calls


@pytest.mark.parametrize('failure', ['fail_state', 'fail_wrap'])
def test_client_configuration_failure_retires_exactly_its_owned_handle(monkeypatch, failure):
    api, native, _ = factory(monkeypatch)
    setattr(native, failure, True)
    with pytest.raises((AgentTaskError, OSError)):
        api.connect()
    assert not native.handles


@pytest.mark.parametrize('failure', ['fail_wait', 'fail_wrap'])
def test_accept_failure_keeps_handles_owned_until_explicit_listener_cleanup(monkeypatch, failure):
    api, native, _ = factory(monkeypatch)
    listener = api.listen()
    setattr(native, failure, True)
    with pytest.raises((AgentTaskError, OSError)):
        listener.accept()
    listener.close()
    assert not native.handles
    if failure == 'fail_wait':
        assert 'cancel' in native.calls


def test_failed_native_handle_retirement_is_retained_for_later_cleanup(monkeypatch):
    api, native, _ = factory(monkeypatch)
    listener = api.listen()
    native.fail_close = True
    with pytest.raises(AgentTaskError):
        listener.close()
    assert len(native.handles) == 1
    native.fail_close = False
    listener.close()
    assert not native.handles


def test_failed_accept_retires_only_failed_instance_and_preserves_the_reserved_listener(monkeypatch):
    api, native, _ = factory(monkeypatch)
    listener = api.listen()
    native.fail_wait = True
    with pytest.raises(OSError):
        listener.accept()
    assert native.handles == {0x100000002}
    native.fail_wait = False
    connection = listener.accept()
    assert connection.fileno() == 0x100000002
    listener.close()
    connection.close()
    assert not native.handles


@pytest.mark.parametrize('operation', ['wait_connected', 'connected'])
def test_internal_factory_refuses_unowned_native_handles_before_any_native_operation(monkeypatch, operation):
    api, native, _ = factory(monkeypatch)
    listener = api.listen()
    try:
        before = list(native.calls)
        with pytest.raises(AgentTaskError):
            getattr(api, operation)(123)
        assert native.calls == before
    finally:
        listener.close()


@pytest.mark.parametrize('raw', [b'x' * 4097, bytearray(b'{}'), {'command': 'input'}],
                         ids=['oversized', 'mutable', 'object'])
def test_connection_only_sends_bounded_immutable_bytes(monkeypatch, raw):
    api, native, _ = factory(monkeypatch)
    connection = api.connect()
    try:
        with pytest.raises(AgentTaskError):
            connection.send_bytes(raw)
        assert not any(isinstance(item, tuple) and item[0] == 'send' for item in native.calls)
        assert not hasattr(connection, 'send') and not hasattr(connection, 'recv')
        connection.send_bytes(b'{}')
        assert ('send', b'{}') in native.calls
        assert len(connection.recv_bytes(4096)) == 4096
        with pytest.raises(AgentTaskError):
            connection.recv_bytes(4097)
    finally:
        connection.close()
