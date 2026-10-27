"""Standard worker host-binding enforcement uses fake targets/readers without any native input."""
import io
import threading

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from .test_agent_presence_runtime import spec

BINDING = {'generation': 'a' * 32, 'lease_id': 'b' * 32}


class Target:
    def ready(self, _spec):
        return True, ''

    def cleanup(self):
        return None


class Gate:
    instances = []

    def __init__(self, binding, takeover):
        self.binding, self.takeover = dict(binding), takeover
        self.retired, self.readies = False, 0
        self.instances.append(self)

    def ready(self):
        self.readies += 1
        self.check()

    def check(self):
        if self.retired:
            raise AgentTaskError('test reader permanently retired')

    def close(self):
        self.retired = True


@pytest.fixture
def worker(monkeypatch):
    from je_auto_control.utils.agent_runtime import native_worker
    monkeypatch.setattr(native_worker, 'DesktopTarget', Target)
    monkeypatch.setattr(native_worker, 'PresenceReader', Gate)
    monkeypatch.setattr(Gate, 'instances', [])
    value = native_worker.NativeWorker(io.BytesIO(), io.BytesIO())
    try:
        yield value
    finally:
        value.close()


def payload(binding=BINDING):
    value = {'spec': spec(), 'owner': {}}
    if binding is not None:
        value['presence'] = dict(binding)
    return value


@pytest.mark.parametrize('binding', [None, {}, {'generation': 'a' * 32},
    {'generation': True, 'lease_id': 'b' * 32}, {**BINDING, 'pid': 42}])
def test_standard_desktop_requires_exact_host_binding_without_starting_old_fallback(worker, binding):
    with pytest.raises(AgentTaskError):
        worker._dispatch('configure', payload(binding))
    assert not Gate.instances


def test_repeated_configure_reuses_one_reader_and_never_acquires_a_new_capability(worker):
    assert worker._dispatch('configure', payload())['ready']
    assert worker._dispatch('configure', payload())['ready']
    assert len(Gate.instances) == 1
    assert Gate.instances[0].binding == BINDING and Gate.instances[0].readies == 2


@pytest.mark.parametrize('change', ['binding', 'spec', 'owner'])
def test_configured_reader_cannot_change_capability_or_host_scope_without_retirement(worker, change):
    worker._dispatch('configure', payload())
    altered = payload()
    if change == 'binding':
        altered['presence']['lease_id'] = 'c' * 32
    if change == 'spec':
        altered['spec']['goal'] = 'a different task'
    if change == 'owner':
        altered['owner'] = {'user_id': 'other', 'role': 'admin', 'store_path': 'not-an-authority'}
    with pytest.raises(AgentTaskError):
        worker._dispatch('configure', altered)
    assert len(Gate.instances) == 1 and Gate.instances[0].binding == BINDING


def test_release_only_cleanup_retires_reader_and_notice_thread_without_rearming(worker):
    worker._dispatch('configure', payload())
    assert worker._release_owned({'keys': [], 'buttons': []}) == {'cleaned': True}
    assert Gate.instances[0].retired and not worker._notice_thread.is_alive()
    with pytest.raises(AgentTaskError):
        worker._dispatch('configure', payload())
    assert len(Gate.instances) == 1


def test_owner_eof_closes_actual_worker_reader_and_notice_lifetime(worker):
    worker._dispatch('configure', payload())
    worker.run()
    assert Gate.instances[0].retired and not worker._notice_thread.is_alive()


def test_notice_start_failure_is_typed_and_closes_unstarted_reader_without_rearming(worker, monkeypatch):
    original = threading.Thread.start

    def start(thread):
        if thread.name == 'AgentPresenceNotice':
            raise RuntimeError('notice admission failed')
        original(thread)

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, 'start', start)
        with pytest.raises(AgentTaskError, match='notice'):
            worker._dispatch('configure', payload())
    assert Gate.instances[0].retired
    with pytest.raises(AgentTaskError):
        worker._dispatch('configure', payload())
    assert len(Gate.instances) == 1
