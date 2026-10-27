"""A contained launcher exiting is insufficient: all actual Job processes must retire first."""
import ctypes
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


class Kernel:
    def __init__(self):
        self.events, self.counts = [], [0]
        self.terminate_ok = self.query_ok = self.close_ok = True
        self.processes, self.handles, self.signals = [], {}, {}
        self.belongs = True

    def CreateJobObjectW(self, *_unused):
        return 0x100000001

    def SetInformationJobObject(self, handle, _kind, _data, _size):
        assert handle == 0x100000001
        return True

    def AssignProcessToJobObject(self, handle, process):
        assert (handle, process) == (0x100000001, 99)
        return True

    def TerminateJobObject(self, handle, _code):
        assert handle == 0x100000001
        self.events.append('terminate')
        return self.terminate_ok

    def QueryInformationJobObject(self, handle, kind, pointer, size, _length):
        assert handle == 0x100000001
        if kind == 3:
            from je_auto_control.utils.agent_runtime.native_job import _ProcessList
            value = ctypes.cast(pointer, ctypes.POINTER(_ProcessList)).contents
            value.assigned = value.listed = len(self.processes)
            for index, pid in enumerate(self.processes):
                value.pids[index] = pid
            return self.query_ok
        assert kind == 1
        from je_auto_control.utils.agent_runtime.native_job import _Accounting
        assert size == ctypes.sizeof(_Accounting) == 48
        value = ctypes.cast(pointer, ctypes.POINTER(_Accounting)).contents
        value.active = self.counts[0]
        if len(self.counts) > 1:
            self.counts.pop(0)
        self.events.append(('active', value.active))
        return self.query_ok

    def CloseHandle(self, handle):
        if handle in self.handles:
            self.events.append(('process-close', self.handles[handle]))
            if self.close_ok:
                del self.handles[handle]
            return self.close_ok
        assert handle == 0x100000001
        self.events.append('close')
        return self.close_ok

    def OpenProcess(self, access, inherit, pid):
        assert access == 0x101000 and not inherit and pid in self.processes
        handle = 0x200000000 + pid
        self.handles[handle] = pid
        return handle

    def IsProcessInJob(self, process, job, pointer):
        assert process in self.handles and job == 0x100000001
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_int)).contents.value = self.belongs
        return True

    def WaitForSingleObject(self, process, milliseconds):
        pid = self.handles[process]
        self.events.append(('process-wait', pid, milliseconds))
        return self.signals.get(pid, 0)


def owned(monkeypatch):
    from je_auto_control.utils.agent_runtime import native_job
    kernel = Kernel()
    monkeypatch.setattr(native_job, '_kernel', lambda: kernel)
    return native_job.NativeJob(SimpleNamespace(_handle=99)), kernel, native_job


def test_job_termination_is_confirmed_empty_before_the_owned_handle_is_closed(monkeypatch):
    job, kernel, _module = owned(monkeypatch)
    kernel.counts = [2, 1, 0]
    job.close()
    assert kernel.events == ['terminate', ('active', 2), ('active', 1), ('active', 0), 'close']
    job.close()
    assert kernel.events.count('close') == 1


@pytest.mark.parametrize('failure', ['terminate_ok', 'query_ok', 'close_ok'])
def test_failed_job_retirement_retains_ownership_and_never_claims_closed(monkeypatch, failure):
    job, kernel, _module = owned(monkeypatch)
    setattr(kernel, failure, False)
    with pytest.raises(AgentTaskError):
        job.close()
    assert job._handle == 0x100000001
    setattr(kernel, failure, True)
    job.close()
    assert job._handle is None


def test_nonempty_tree_exhausts_original_bound_and_remains_owned(monkeypatch):
    job, kernel, module = owned(monkeypatch)
    kernel.counts = [1]
    now = [0.0]
    sleeps = []

    def sleep(delay):
        sleeps.append(delay)
        now[0] += delay

    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: now[0], sleep=sleep), raising=False)
    with pytest.raises(AgentTaskError):
        job.close(timeout=0.03)
    assert now[0] <= 0.03 and sleeps
    assert job._handle == 0x100000001 and 'close' not in kernel.events
    kernel.counts = [0]
    job.close()
    assert job._handle is None


def test_job_and_launcher_reaping_share_one_original_three_second_deadline(monkeypatch):
    from je_auto_control.utils.agent_runtime import native_channel
    now, observed = [0.0], []

    def close(*, timeout):
        observed.append(('job', timeout))
        now[0] += 2

    instance = object.__new__(native_channel.OwnedChannel)
    instance._job = SimpleNamespace(close=close)
    instance._process = SimpleNamespace(wait=lambda *, timeout: observed.append(('process', timeout)))
    monkeypatch.setattr(native_channel, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(native_channel, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    instance._stop_process()
    assert observed == [('job', 3), ('process', 1)]


def test_process_objects_must_signal_even_after_the_job_reports_no_active_processes(monkeypatch):
    job, kernel, _module = owned(monkeypatch)
    kernel.processes = [201, 202]
    kernel.signals[202] = 258
    with pytest.raises(AgentTaskError):
        job.close(timeout=0.03)
    assert job._handle == 0x100000001 and 'close' not in kernel.events
    assert any(event[:2] == ('process-wait', 202) for event in kernel.events if isinstance(event, tuple))
    assert kernel.handles
    kernel.processes = []
    kernel.signals[202] = 0
    job.close()
    assert job._handle is None and not kernel.handles


def test_process_object_queries_may_never_select_a_process_outside_the_actual_owned_job(monkeypatch):
    job, kernel, _module = owned(monkeypatch)
    kernel.processes, kernel.belongs = [201], False
    with pytest.raises(AgentTaskError):
        job.close()
    assert 'terminate' in kernel.events and 'close' not in kernel.events
    assert not kernel.handles


def test_member_capture_cannot_spend_past_the_original_retirement_deadline(monkeypatch):
    job, kernel, module = owned(monkeypatch)
    kernel.processes = list(range(201, 301))
    now = [0.0]
    original = kernel.OpenProcess

    def delayed(*args):
        now[0] += 0.01
        return original(*args)

    monkeypatch.setattr(kernel, 'OpenProcess', delayed)
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    with pytest.raises(AgentTaskError):
        job.close(timeout=0.03)
    assert now[0] <= 0.03 and 'terminate' in kernel.events
    assert job._handle is not None and 'close' not in kernel.events


def test_already_exhausted_deadline_still_terminates_only_the_owned_job(monkeypatch):
    job, kernel, _module = owned(monkeypatch)
    kernel.counts = [1]
    with pytest.raises(AgentTaskError):
        job.close(timeout=0)
    assert 'terminate' in kernel.events and 'close' not in kernel.events
    assert job._handle == 0x100000001
