"""The native source actor runs fake observation APIs only, with real bounded request waits."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError


class FakeAPI:
    def __init__(self):
        self.clock = 0.0
        self.threads = []
        self.opened = self.closed = 0
        self.physical = None
        self.emit = self.fail_open = self.fail_poll = self.fail_close = False
        self.block_fresh_only = False
        self.block = threading.Event()
        self.blocked = threading.Event()
        self.allow = threading.Event()
        self.allow.set()

    def open(self, callback):
        self.threads.append(threading.get_ident())
        self.opened += 1
        self.physical = callback
        if self.fail_open:
            raise AgentTaskError('synthetic native start failure')

    def poll(self, timeout):
        self.threads.append(threading.get_ident())
        if self.block.is_set() and (not self.block_fresh_only or timeout == 0):
            self.blocked.set()
            assert self.allow.wait(2)
        if self.fail_poll:
            raise AgentTaskError('synthetic native poll failure')
        self.clock += 0.125
        if self.emit:
            self.emit = False
            self.physical()
        time.sleep(0)
        return True, False

    def close(self):
        self.threads.append(threading.get_ident())
        self.closed += 1
        if self.fail_close:
            raise AgentTaskError('synthetic native retirement failure')


def actor(api):
    from je_auto_control.utils.agent_runtime.presence_windows import WindowsPresenceSource
    return WindowsPresenceSource(lambda: api, lambda: api.clock)


def lease(source):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            return source.request('acquire', {})
        except AgentControlBusy:
            threading.Event().wait(0.001)
    pytest.fail('synthetic observer never acquired its verified sixty-second idle')


def test_inert_inspection_does_not_create_a_native_api_or_thread():
    api = FakeAPI()
    source = actor(api)
    assert source.request('inspect', {})['state'] == 'not_started'
    assert api.opened == 0
    source.close()
    assert api.closed == 0
    with pytest.raises(AgentTaskError):
        source.start()


def test_source_keeps_one_generation_and_revalidates_fresh_physical_events():
    api = FakeAPI()
    source = actor(api)
    try:
        source.start()
        first = lease(source)
        assert source.request('check', first)['state'] == 'monitoring'
        api.emit = True
        with pytest.raises(AgentTaskError, match='resume'):
            source.request('check', first)
        second = lease(source)
        assert first['generation'] == second['generation']
        assert first['lease_id'] != second['lease_id']
        assert source.request('release', first) == {'released': True}
        assert source.request('check', second)['native_evidence'] == 'not_recorded'
    finally:
        source.close()
    assert api.opened == api.closed == 1
    assert len(set(api.threads)) == 1
    assert api.threads[0] != threading.get_ident()


def test_start_failure_retires_partial_api_and_never_rearms():
    api = FakeAPI()
    api.fail_open = True
    source = actor(api)
    with pytest.raises(AgentTaskError):
        source.start()
    assert api.closed == 1
    source.close()
    with pytest.raises(AgentTaskError):
        source.request('acquire', {})


def test_start_after_a_later_native_failure_cannot_claim_a_ready_source():
    api = FakeAPI()
    source = actor(api)
    source.start()
    api.fail_poll = True
    source._thread.join(timeout=1)
    assert not source._thread.is_alive()
    try:
        with pytest.raises(AgentTaskError):
            source.start()
    finally:
        source.close()


def test_startup_wait_failure_retires_instead_of_leaving_a_monitor_running(monkeypatch):
    api = FakeAPI()
    source = actor(api)
    monkeypatch.setattr(source._ready, 'wait', lambda _timeout: False)
    try:
        with pytest.raises(AgentTaskError):
            source.start()
        assert not source._thread.is_alive()
        assert api.opened == api.closed
    finally:
        source.close()


def test_timed_out_request_does_not_allocate_a_late_lease():
    api = FakeAPI()
    source = actor(api)
    try:
        source.start()
        first = lease(source)
        api.allow.clear()
        api.block.set()
        assert api.blocked.wait(1)
        with pytest.raises(AgentTaskError, match='deadline'):
            source.request('acquire', {}, timeout=0.05)
        api.block.clear()
        api.allow.set()
        source.request('inspect', {})
        assert len(source._state._leases) == 1
        assert source.request('check', first)['state'] == 'monitoring'
    finally:
        api.allow.set()
        source.close()


def test_timeout_during_fresh_native_poll_cannot_create_even_a_temporary_late_lease(monkeypatch):
    api = FakeAPI()
    source = actor(api)
    calls = []
    try:
        source.start()
        lease(source)
        original = source._state.acquire
        monkeypatch.setattr(source._state, 'acquire', lambda: calls.append(True) or original())
        api.block_fresh_only = True
        api.allow.clear()
        api.block.set()
        with pytest.raises(AgentTaskError, match='deadline'):
            source.request('acquire', {}, timeout=0.05)
        assert api.blocked.is_set()
        api.block.clear()
        api.allow.set()
        source.request('inspect', {})
        assert calls == []
    finally:
        api.allow.set()
        source.close()


def test_close_during_blocked_native_poll_reports_unretired_source():
    api = FakeAPI()
    source = actor(api)
    source.start()
    api.allow.clear()
    api.block.set()
    assert api.blocked.wait(1)
    try:
        with pytest.raises(AgentTaskError, match='retir'):
            source.close()
        with pytest.raises(AgentTaskError):
            source.request('acquire', {})
    finally:
        api.allow.set()
        source._thread.join(timeout=1)
    assert not source._thread.is_alive()


def test_native_cleanup_failure_remains_visible_to_the_owner():
    api = FakeAPI()
    source = actor(api)
    source.start()
    api.fail_close = True
    with pytest.raises(AgentTaskError, match='retir'):
        source.close()


def test_unretired_native_api_stays_owned_after_observer_thread_exits():
    import gc
    import weakref
    from je_auto_control.utils.agent_runtime.presence_windows import WindowsPresenceSource
    api = FakeAPI()
    reference = weakref.ref(api)
    api.fail_close = True
    allocation = [api]
    source = WindowsPresenceSource(lambda: allocation.pop(), lambda: 0.0)
    source.start()
    del api
    with pytest.raises(AgentTaskError, match='retir'):
        source.close()
    gc.collect()
    assert reference() is not None


def test_request_waiting_for_source_mutex_keeps_its_original_deadline():
    source = actor(FakeAPI())
    source.start()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            with source._mutex:
                future = executor.submit(source.request, 'inspect', {}, 0.05)
                with pytest.raises(AgentTaskError, match='deadline'):
                    future.result(timeout=0.5)
    finally:
        source.close()


def test_close_racing_first_start_cannot_leave_a_live_native_source():
    api = FakeAPI()
    source = actor(api)
    barrier = threading.Barrier(2)

    def start():
        barrier.wait(timeout=1)
        try:
            source.start()
        except AgentTaskError:
            pass

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(start)
        barrier.wait(timeout=1)
        source.close()
        future.result(timeout=1)
    assert api.opened == api.closed
    with pytest.raises(AgentTaskError):
        source.start()


def test_request_queue_refuses_seventeenth_client_without_extending_deadlines():
    api = FakeAPI()
    source = actor(api)
    source.start()
    api.allow.clear()
    api.block.set()
    assert api.blocked.wait(1)

    def inspect():
        try:
            return source.request('inspect', {})
        except AgentTaskError:
            return None

    try:
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(inspect) for _index in range(16)]
            deadline = time.monotonic() + 0.15
            while source._queue.qsize() < 16 and time.monotonic() < deadline:
                time.sleep(0)
            assert source._queue.qsize() == 16
            with pytest.raises(AgentControlBusy, match='capacity'):
                source.request('inspect', {})
            api.block.clear()
            api.allow.set()
            assert all(future.result(timeout=1) is not None for future in futures)
    finally:
        api.allow.set()
        source.close()


def test_new_source_import_construction_and_status_add_no_native_dll_loads(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    import je_auto_control
    origin = Path(je_auto_control.__file__).resolve().parent.parent
    code = '''
import ctypes, pathlib, sys
import je_auto_control
assert "je_auto_control.utils.agent_runtime.presence_win32" not in sys.modules
assert "je_auto_control.utils.agent_runtime.presence_windows" not in sys.modules
def forbidden(*args, **kwargs): raise AssertionError("native DLL lookup during inert inspection")
ctypes.WinDLL = forbidden
from je_auto_control.utils.agent_runtime import presence_win32, presence_windows
assert pathlib.Path(presence_win32.__file__).resolve().is_relative_to(pathlib.Path(sys.argv[1]))
api = presence_win32.Win32PresenceAPI()
source = presence_windows.WindowsPresenceSource()
assert source.request("inspect", {})["state"] == "not_started"
assert api.registrations() == set()
source.close()
api.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(origin)], cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(origin), PYTHONUTF8='1'), capture_output=True,
        timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')


@pytest.mark.parametrize('operation,body', [('unknown', {}), ('inspect', {'extra': 1}),
    ('acquire', {'idle_seconds': 60}), ('check', {'generation': True, 'lease_id': 'x'}),
    ('release', None)])
def test_invalid_source_requests_never_start_native_observation(operation, body):
    api = FakeAPI()
    source = actor(api)
    try:
        with pytest.raises(AgentTaskError):
            source.request(operation, body)
        assert api.opened == 0
    finally:
        source.close()


@pytest.mark.parametrize('timeout', [True, 0, -1, float('nan'), float('inf'), 1])
def test_source_request_deadline_is_finite_typed_and_never_extended(timeout):
    source = actor(FakeAPI())
    try:
        with pytest.raises(AgentTaskError):
            source.request('inspect', {}, timeout=timeout)
    finally:
        source.close()
