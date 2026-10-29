"""Real runtimes/standard workers share a virtual source through actual owned processes and secured pipes."""
from contextlib import closing
from pathlib import Path
import sys
import time

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.agent_runtime.presence_pool import PresencePool
from .test_agent_presence_runtime import spec
from .test_agent_presence_service_ipc import create, setup

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='actual Windows runtime/worker/pipe integration')
ROOT = Path(__file__).resolve().parents[3]


def worker_script(namespace, directory):
    return f'''
import sys
from pathlib import Path
from types import SimpleNamespace
from je_auto_control.utils.agent_runtime import native_worker
from je_auto_control.utils.agent_runtime.presence_reader import PresenceReader
from je_auto_control.utils.agent_runtime.presence_pipe_windows import WindowsPresencePipe
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.wrapper import auto_control_keyboard as keyboard
expected = Path({str(ROOT / 'je_auto_control/utils/agent_runtime/native_worker.py')!r})
assert Path(native_worker.__file__).resolve() == expected
directory = Path({str(directory)!r})

def release(*_args, **_kwargs):
    if (directory / 'cleanup-fail').exists():
        raise AutoControlException('test keyboard release failed')
    with (directory / 'input-events.txt').open('a', encoding='utf-8') as output:
        output.write('released\\n')

def press(*_args, **_kwargs):
    with (directory / 'input-events.txt').open('a', encoding='utf-8') as output:
        output.write('pressed\\n')

keyboard.keyboard = SimpleNamespace(press_key=press, release_key=release, release_unicode=release)

class NoNativeDesktop:
    def ready(self, spec):
        self.spec = spec
        return True, ''
    def observe(self):
        return {{'identity': 'fixture', 'value': 0}}
    def cleanup(self):
        pass
    def validate_input(self, event):
        pass
    def perform(self, name, arguments):
        keyboard.press_keyboard_key(65, skip_record=True)
        return {{'ok': True}}

def reader(binding, takeover):
    return PresenceReader(binding, takeover, pipe=WindowsPresencePipe(namespace={namespace!r}))

native_worker.DesktopTarget = NoNativeDesktop
native_worker.PresenceReader = reader
native_worker.NativeWorker(sys.stdin.buffer, sys.stdout.buffer).run()
'''


class Fixture:
    def __init__(self, monkeypatch, tmp_path):
        from je_auto_control.utils.agent_runtime import native_target, presence_pool
        self.namespace, self.clock, self.instances = setup(tmp_path)
        self.tmp_path = tmp_path
        self.sources, self.helpers = [], []
        self.pool = PresencePool(channel_factory=self.source)
        self.pools = [self.pool]
        monkeypatch.setattr(presence_pool, '_SHARED', presence_pool._Registry(pool=self.pool))
        monkeypatch.setattr(presence_pool, 'PresencePool', self.new_pool)
        monkeypatch.setattr(native_target, 'owned_channel', self.helper)

    def source(self, argv):
        assert argv[-2:] == ['-m', 'je_auto_control.utils.agent_runtime.presence_broker']
        channel = create(self.namespace, self.clock, self.instances)
        self.sources.append(channel)
        return channel

    def new_pool(self):
        self.pool = PresencePool(channel_factory=self.source)
        self.pools.append(self.pool)
        return self.pool

    def helper(self, argv, **kwargs):
        assert tuple(argv[-2:]) == ('-m', 'je_auto_control.utils.agent_runtime.native_worker')
        assert kwargs.pop('display') is True  # A desktop helper never goes to the owner service.
        channel = OwnedChannel([sys.executable, '-u', '-c', worker_script(self.namespace, self.tmp_path)], **kwargs)
        self.helpers.append(channel)
        return channel

    def runtime(self, name):
        target = NativeDesktopTarget(resource_path=self.tmp_path / 'input.lock')
        return AgentRuntime(self.tmp_path / (name + '.sqlite'), targets={'local-desktop': target}), target

    def first_observation(self, runtime, task):
        with pytest.raises(AgentControlBusy):
            runtime.observe(task.task_id)
        self.clock.write_text('60', encoding='utf-8')
        return runtime.observe(task.task_id)

    def retired(self):
        return all(pool.retired for pool in self.pools) and all(
            channel.retired for channel in self.sources + self.helpers)


def test_actual_two_runtime_databases_and_standard_helpers_share_idle_and_source_ownership(monkeypatch, tmp_path):
    fixture = Fixture(monkeypatch, tmp_path)
    first, left_target = fixture.runtime('one')
    second, right_target = fixture.runtime('two')
    try:
        left, right = first.submit(spec()), second.submit(spec())
        assert not fixture.sources and not fixture.helpers
        fixture.first_observation(first, left)
        old = dict(left_target._presence._grant.binding)
        first.pause(left.task_id)
        second.observe(right.task_id)
        current = dict(right_target._presence._grant.binding)
        assert current['generation'] == old['generation'] and current['lease_id'] != old['lease_id']
        assert len(fixture.sources) == 1 and len(fixture.instances.read_text().splitlines()) == 1
        first.close()
        assert not fixture.sources[0].retired
        second.observe(right.task_id)
        assert right_target._presence._grant.binding == current
        assert len(fixture.helpers) == 3
    finally:
        first.close()
        second.close()
    assert fixture.retired()


def test_actual_worker_watch_notice_pauses_and_explicit_resume_waits_fresh_idle(monkeypatch, tmp_path):
    fixture = Fixture(monkeypatch, tmp_path)
    runtime, target = fixture.runtime('one')
    with closing(runtime):
        task = runtime.submit(spec())
        fixture.first_observation(runtime, task)
        original = dict(target._presence._grant.binding)
        (tmp_path / 'physical.txt').write_text('physical-event-1', encoding='utf-8')
        deadline = time.monotonic() + 3
        while runtime.get(task.task_id).state != 'paused' and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runtime.get(task.task_id).state == 'paused' and not runtime._leases
        assert target._channel is None and target._ledger.empty
        assert not fixture.sources[0].retired
        runtime.resume(task.task_id)
        with pytest.raises(AgentControlBusy):
            runtime.observe(task.task_id)
        fixture.clock.write_text('120', encoding='utf-8')
        runtime.observe(task.task_id)
        current = target._presence._grant.binding
        assert current['generation'] == original['generation'] and current['lease_id'] != original['lease_id']
        assert len(fixture.sources) == 1 and len(fixture.instances.read_text().splitlines()) == 1
    assert fixture.retired()


def test_actual_source_owner_loss_requires_new_generation_and_explicit_fresh_idle_resume(monkeypatch, tmp_path):
    fixture = Fixture(monkeypatch, tmp_path)
    runtime, target = fixture.runtime('one')
    with closing(runtime):
        task = runtime.submit(spec())
        fixture.first_observation(runtime, task)
        previous = dict(target._presence._grant.binding)
        fixture.sources[0].close()
        deadline = time.monotonic() + 3
        while (runtime.get(task.task_id).state != 'paused' or not fixture.pools[0].retired
               ) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runtime.get(task.task_id).state == 'paused' and fixture.pools[0].retired
        assert len(fixture.sources) == 1 and target._channel is None
        runtime.resume(task.task_id)
        with pytest.raises(AgentControlBusy):
            runtime.observe(task.task_id)
        fixture.clock.write_text('120', encoding='utf-8')
        runtime.observe(task.task_id)
        assert target._presence._grant.binding['generation'] != previous['generation']
        assert len(fixture.sources) == 2 and len(fixture.instances.read_text().splitlines()) == 2
    assert fixture.retired()


def test_actual_reader_loss_cannot_release_input_lease_until_owned_ack_cleanup_succeeds(monkeypatch, tmp_path):
    fixture = Fixture(monkeypatch, tmp_path)
    runtime, target = fixture.runtime('one')
    definition = {**spec(), 'allowed_tools': ['AC_press_keyboard_key']}
    failed = tmp_path / 'cleanup-fail'
    with closing(runtime):
        task = runtime.submit(definition)
        frame = fixture.first_observation(runtime, task)
        runtime.act(task.task_id, {'tool': 'AC_press_keyboard_key', 'arguments': {'keycode': 65},
                                   'observation_id': frame.observation_id})
        assert not target._ledger.empty
        failed.write_text('fail', encoding='utf-8')
        (tmp_path / 'physical.txt').write_text('physical-event-1', encoding='utf-8')
        deadline = time.monotonic() + 3
        while (target._channel is not None and not target._channel.retired) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runtime.get(task.task_id).state == 'pausing' and runtime._leases
        deadline = time.monotonic() + 1
        while target.presence_status['takeover']['cleanup_error'] is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert target.presence_status['takeover']['cleanup_error'] == 'AgentTaskError'
        assert not target._ledger.empty and target._resource is not None and target._presence._grant is not None
        with pytest.raises(AgentTaskError):
            runtime.resume(task.task_id)
        other = runtime.submit(spec())
        with pytest.raises(AgentControlBusy):
            runtime.observe(other.task_id)
        failed.unlink()
        runtime.pause(task.task_id)
        assert runtime.get(task.task_id).state == 'paused' and not runtime._leases and target._ledger.empty
        assert target._resource is None and target._presence._grant is None
        fixture.clock.write_text('120', encoding='utf-8')
        runtime.observe(other.task_id)
        assert (tmp_path / 'input-events.txt').read_text().splitlines() == ['pressed', 'released']
        assert len(fixture.sources) == 1
    assert fixture.retired()
