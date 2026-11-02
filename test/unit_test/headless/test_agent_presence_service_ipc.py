"""Two actual contained brokers share a native pipe source with explicit virtual idle, never native input."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import secrets
import sys
import time

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='actual Windows source/broker pipe integration')
ROOT = Path(__file__).resolve().parents[3]


def script(namespace, clock, instances):
    source = f'''
import json, sys, threading
from pathlib import Path
sys.path.insert(0, {str(ROOT / 'test/unit_test/headless')!r})
from presence_test_support import Source
from je_auto_control.utils.agent_runtime import presence_worker
expected = Path({str(ROOT / 'je_auto_control/utils/agent_runtime/presence_worker.py')!r})
assert Path(presence_worker.__file__).resolve() == expected

class ControlledSource(Source):
    def __init__(self):
        super().__init__()
        self.base = float(Path({str(clock)!r}).read_text())
        self.lock = threading.RLock()
        self.input_version = ''
    def start(self):
        super().start()
        with Path({str(instances)!r}).open('a', encoding='utf-8') as output:
            output.write(json.dumps({{'generation': self.status()['generation']}}) + '\\n')
    def request(self, operation, body):
        gate = Path({str(clock.parent / 'acquire-gate')!r})
        if operation == 'acquire' and gate.exists():
            Path({str(clock.parent / 'acquire-entered')!r}).write_text('entered')
            while gate.exists():
                threading.Event().wait(0.01)
        with self.lock:
            age = float(Path({str(clock)!r}).read_text()) - self.base
            if age < self.now:
                raise RuntimeError('controlled source clock regressed')
            self.advance(age - self.now)
            marker = Path({str(clock.parent / 'physical.txt')!r})
            version = marker.read_text() if marker.exists() else ''
            if version and version != self.input_version:
                self.state.physical()
                self.input_version = version
            return super().request(operation, body)
    def release(self, **body):
        super().release(**body)
        with Path({str(clock.parent / 'releases.txt')!r}).open('a', encoding='utf-8') as output:
            output.write('released\\n')

presence_worker.run(sys.stdin.buffer, sys.stdout.buffer, source_factory=ControlledSource)
'''
    return f'''
import sys
from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel
from je_auto_control.utils.agent_runtime.presence_worker import SourceProcess
from je_auto_control.utils.agent_runtime.presence_broker import PresenceBroker, run

def source_channel(_fixed_argv):
    return OwnedChannel([sys.executable, '-u', '-c', {source!r}])

broker = PresenceBroker(namespace={namespace!r},
    launch=lambda: SourceProcess({namespace!r}, channel_factory=source_channel))
run(sys.stdin.buffer, sys.stdout.buffer, broker)
'''


def create(namespace, clock, instances):
    return OwnedChannel([sys.executable, '-u', '-c', script(namespace, clock, instances)])


def setup(tmp_path):
    namespace = secrets.token_hex(16)
    clock, instances = tmp_path / 'clock.txt', tmp_path / 'instances.jsonl'
    clock.write_text('0', encoding='utf-8')
    instances.write_text('', encoding='utf-8')
    return namespace, clock, instances


def wait_lost(broker, lease):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = broker.request('check', lease, timeout=max(0.001, deadline - time.monotonic()))
        if result['status'] == 'lease_lost':
            return
    pytest.fail('disconnected borrower presence lease did not retire within3seconds')


def test_two_actual_brokers_share_generation_busy_and_borrower_only_token_cleanup(tmp_path):
    namespace, clock, instances = setup(tmp_path)
    owner, borrower = create(namespace, clock, instances), create(namespace, clock, instances)
    try:
        ready = owner.request('bootstrap', {}, timeout=15)
        assert borrower.request('bootstrap', {}, timeout=15) == ready
        assert owner.request('acquire', {}, timeout=3)['status'] == 'busy'
        assert not owner.retired and len(instances.read_text().splitlines()) == 1
        clock.write_text('60', encoding='utf-8')
        first = owner.request('acquire', {}, timeout=3)['result']
        second = borrower.request('acquire', {}, timeout=3)['result']
        assert first['generation'] == second['generation'] == ready['generation']
        borrower.close()
        wait_lost(owner, second)
        assert owner.request('check', first, timeout=3)['status'] == 'ok'
        assert owner.request('inspect', {}, timeout=3)['result']['generation'] == ready['generation']
        assert len(instances.read_text().splitlines()) == 1
    finally:
        borrower.close()
        owner.close()
    assert borrower.retired and owner.retired


def test_actual_owner_loss_refuses_old_leases_and_replacement_observes_fresh_idle(tmp_path):
    namespace, clock, instances = setup(tmp_path)
    owner, borrower = create(namespace, clock, instances), create(namespace, clock, instances)
    replacement = None
    try:
        ready = owner.request('bootstrap', {}, timeout=15)
        borrower.request('bootstrap', {}, timeout=15)
        clock.write_text('60', encoding='utf-8')
        old = borrower.request('acquire', {}, timeout=3)['result']
        owner.close()
        with pytest.raises(AgentTaskError):
            borrower.request('check', old, timeout=3)
        assert borrower.retired and len(instances.read_text().splitlines()) == 1
        replacement = create(namespace, clock, instances)
        new = replacement.request('bootstrap', {}, timeout=15)
        assert new['generation'] != ready['generation']
        assert replacement.request('acquire', {}, timeout=3)['status'] == 'busy'
        assert replacement.request('check', old, timeout=3)['status'] == 'lease_lost'
        clock.write_text('120', encoding='utf-8')
        assert replacement.request('acquire', {}, timeout=3)['result']['generation'] == new['generation']
        assert len(instances.read_text().splitlines()) == 2
    finally:
        if replacement is not None:
            replacement.close()
        borrower.close()
        owner.close()


def test_concurrent_actual_startup_constructs_only_the_first_instance_source(tmp_path):
    namespace, clock, instances = setup(tmp_path)
    first, second = create(namespace, clock, instances), create(namespace, clock, instances)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            left = pool.submit(first.request, 'bootstrap', {}, timeout=15)
            right = pool.submit(second.request, 'bootstrap', {}, timeout=15)
            assert left.result(timeout=16) == right.result(timeout=16)
        records = [json.loads(line) for line in instances.read_text().splitlines()]
        assert len(records) == 1 and records[0]['generation'] == left.result()['generation']
        assert first.request('acquire', {}, timeout=3)['status'] == 'busy'
        assert second.request('acquire', {}, timeout=3)['status'] == 'busy'
    finally:
        first.close()
        second.close()


def wait_file(path):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if path.exists() and path.read_text():
            return
        time.sleep(0.01)
    pytest.fail('owned fake-source observation did not arrive within3seconds')


def test_borrower_lost_during_acquire_revokes_late_token_without_stopping_the_owner(tmp_path):
    namespace, clock, instances = setup(tmp_path)
    owner, borrower = create(namespace, clock, instances), create(namespace, clock, instances)
    gate = tmp_path / 'acquire-gate'
    try:
        ready = owner.request('bootstrap', {}, timeout=15)
        borrower.request('bootstrap', {}, timeout=15)
        clock.write_text('60', encoding='utf-8')
        lease = owner.request('acquire', {}, timeout=3)['result']
        gate.write_text('block', encoding='utf-8')
        with ThreadPoolExecutor(max_workers=1) as pool:
            waiting = pool.submit(borrower.request, 'acquire', {}, timeout=0.25)
            wait_file(tmp_path / 'acquire-entered')
            with pytest.raises(AgentTaskError, match='deadline'):
                waiting.result(timeout=4)
        assert borrower.retired and not owner.retired
        gate.unlink()
        wait_file(tmp_path / 'releases.txt')
        assert owner.request('check', lease, timeout=3)['status'] == 'ok'
        assert owner.request('inspect', {}, timeout=3)['result']['generation'] == ready['generation']
        assert len(instances.read_text().splitlines()) == 1
    finally:
        gate.unlink(missing_ok=True)
        borrower.close()
        owner.close()
