"""Presence endpoint identity uses query-only native process handles, never JSON-selected PIDs."""
import ctypes
import sys
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


class Function:
    def __init__(self, body):
        self.body, self.calls = body, []

    def __call__(self, *args):
        self.calls.append(args)
        return self.body(*args)


class Native:
    def __init__(self, module):
        self.module = module
        self.sid = 'S-1-5-21-1'
        self.peer_sid = self.sid
        self.peer_session = 2
        self.live = True
        self.required = 64
        self.token_ok = self.info_ok = True
        self.handles, self.buffers = {}, {}
        self.kernel = SimpleNamespace(
            GetCurrentProcessId=Function(lambda: 10), OpenProcess=Function(self.open),
            CloseHandle=Function(self.close), ProcessIdToSessionId=Function(self.session),
            GetProcessTimes=Function(self.times), LocalFree=Function(self.free),
            WaitForSingleObject=Function(lambda *_: 258 if self.live else 0),
            GetNamedPipeServerProcessId=Function(self.peer), GetNamedPipeClientProcessId=Function(self.peer))
        self.advapi = SimpleNamespace(OpenProcessToken=Function(self.token), GetTokenInformation=Function(self.info),
            IsValidSid=Function(lambda *_: True), ConvertSidToStringSidW=Function(self.sid_string),
            ConvertStringSecurityDescriptorToSecurityDescriptorW=Function(self.descriptor))

    def open(self, access, inherit, pid):
        assert access == 0x101000 and not inherit
        handle = 0x100000000 + pid
        self.handles[handle] = pid
        return handle

    def close(self, handle):
        assert handle in self.handles
        del self.handles[handle]
        return True

    def session(self, pid, pointer):
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32)).contents.value = 2 if pid == 10 else self.peer_session
        return True

    def times(self, handle, created, *_others):
        value = ctypes.cast(created, ctypes.POINTER(self.module._FileTime)).contents
        value.low, value.high = self.handles[handle], 1
        return True

    def peer(self, _pipe, pointer):
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32)).contents.value = 11
        return True

    def token(self, handle, access, pointer):
        assert access == 8
        if not self.token_ok:
            return False
        value = handle + 0x100000000
        self.handles[value] = self.handles[handle]
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p)).contents.value = value
        return True

    def info(self, handle, category, buffer, _size, needed):
        assert category == 1
        ctypes.cast(needed, ctypes.POINTER(ctypes.c_uint32)).contents.value = self.required
        if buffer is None or not self.info_ok:
            return False
        value = ctypes.cast(buffer, ctypes.POINTER(self.module._TokenUser)).contents
        value.sid = 0x100 + self.handles[handle]
        return True

    def sid_string(self, sid, output):
        text = self.sid if sid == 0x10A else self.peer_sid
        buffer = ctypes.create_unicode_buffer(text)
        pointer = ctypes.addressof(buffer)
        self.buffers[pointer] = buffer
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = pointer
        return True

    def descriptor(self, _text, revision, output, _size):
        assert revision == 1
        buffer = ctypes.create_string_buffer(64)
        pointer = ctypes.addressof(buffer)
        self.buffers[pointer] = buffer
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = pointer
        return True

    def free(self, handle):
        pointer = handle.value if isinstance(handle, ctypes.c_void_p) else handle
        assert pointer in self.buffers
        del self.buffers[pointer]
        return None


def native():
    from je_auto_control.utils.agent_runtime import presence_security_windows as module
    fake = Native(module)
    api = module.WindowsPresenceSecurity((fake.kernel, fake.advapi))
    return api, fake


def test_constructor_is_inert_and_current_identity_releases_all_query_handles():
    api, fake = native()
    assert not fake.kernel.OpenProcess.calls
    value = api.current()
    assert (value.pid, value.sid, value.session, value.birth) == (10, fake.sid, 2, (1 << 32) + 10)
    assert not fake.handles and not fake.buffers
    assert fake.kernel.OpenProcess.restype is ctypes.c_void_p


@pytest.mark.parametrize('server', [True, False])
def test_peer_identity_comes_from_connected_pipe_and_only_owned_handles_are_closed(server):
    api, fake = native()
    peer = api.peer(999, server=server)
    assert peer.identity.pid == 11 and peer.identity.birth == (1 << 32) + 11
    assert peer.alive()
    getter = fake.kernel.GetNamedPipeClientProcessId if server else fake.kernel.GetNamedPipeServerProcessId
    assert len(getter.calls) == 1
    assert len(fake.handles) == 1
    peer.close()
    peer.close()
    assert not peer.alive()
    assert not fake.handles and not fake.buffers


@pytest.mark.parametrize('attribute,value', [('peer_sid', 'S-1-5-21-2'), ('peer_session', 3), ('live', False)])
def test_wrong_os_user_session_or_dead_peer_is_refused_without_process_termination(attribute, value):
    api, fake = native()
    setattr(fake, attribute, value)
    with pytest.raises(AgentTaskError):
        api.peer(999, server=False)
    assert not fake.handles and not fake.buffers


@pytest.mark.parametrize('attribute,value', [('token_ok', False), ('info_ok', False),
    ('required', 0), ('required', 1), ('required', 65537), ('sid', 'S-1-5-21-1)(A;;GA;;;WD')])
def test_invalid_token_data_cannot_select_endpoint_or_descriptor_and_keeps_no_handles(attribute, value):
    api, fake = native()
    setattr(fake, attribute, value)
    with pytest.raises(AgentTaskError):
        api.current()
    assert not fake.handles and not fake.buffers
    assert not fake.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.calls


def test_pipe_security_descriptor_grants_only_current_user_system_and_is_not_inheritable():
    api, fake = native()
    with api.attributes() as value:
        assert value.length == ctypes.sizeof(type(value))
        assert value.inherit == 0 and value.descriptor
        assert len(fake.buffers) == 1
        text = fake.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.calls[0][0]
        assert text == 'D:P(A;;GA;;;SY)(A;;GA;;;S-1-5-21-1)'
    assert not fake.handles and not fake.buffers


def test_endpoint_is_derived_from_actual_sid_session_and_survives_process_restart():
    api, fake = native()
    name = api.name()
    assert name.startswith('\\\\.\\pipe\\je-auto-presence-v1-')
    assert fake.sid not in name
    api.peer(999, server=False).close()
    assert api.name() == name
    fake.sid = 'S-1-5-21-5'
    assert api.name() != name


@pytest.mark.skipif(sys.platform != 'win32', reason='native process-token identity is Windows-only')
def test_real_current_process_identity_is_query_only_and_never_starts_observation():
    import os
    from je_auto_control.utils.agent_runtime.presence_security_windows import WindowsPresenceSecurity
    api = WindowsPresenceSecurity()
    value = api.current()
    assert value.pid == os.getpid()
    assert value.sid.startswith('S-1-') and value.birth > 0 and value.session >= 0
    with api.attributes() as attributes:
        assert attributes.descriptor and not attributes.inherit
