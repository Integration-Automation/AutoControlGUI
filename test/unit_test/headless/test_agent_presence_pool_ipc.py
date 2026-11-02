"""Actual owned pool/broker/pipe lifetimes with an explicitly virtual source, never desktop input."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
import sys
import threading

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.presence_pool import PresencePool
from .test_agent_presence_service_ipc import create, setup, wait_file, wait_lost

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='actual Windows owned pool/pipe integration')


def noop():
    return None


def instance(namespace, clock, instances, channels):
    def factory(argv):
        assert argv == [sys.executable, '-u', '-m', 'je_auto_control.utils.agent_runtime.presence_broker']
        channel = create(namespace, clock, instances)
        channels.append(channel)
        return channel

    return PresencePool(channel_factory=factory)


def test_actual_pool_retains_one_source_across_reference_and_borrower_replacement(tmp_path):
    namespace, clock, instances = setup(tmp_path)
    channels = []
    owner = instance(namespace, clock, instances, channels)
    first, second = owner.reference(), owner.reference()
    borrower = instance(namespace, clock, instances, channels)
    other = borrower.reference()
    verifier = None
    try:
        with pytest.raises(AgentControlBusy):
            first.acquire(noop, 15)
        clock.write_text('60', encoding='utf-8')
        left, right = first.acquire(noop, 3), second.acquire(noop, 3)
        borrowed = other.acquire(noop, 15)
        assert left['generation'] == right['generation'] == borrowed['generation']
        verifier = create(namespace, clock, instances)
        verifier.request('bootstrap', {}, timeout=15)
        first.close()
        wait_lost(verifier, left)
        assert verifier.request('check', right, timeout=3)['status'] == 'ok'
        other.close()
        assert borrower.retired and channels[1].retired and not channels[0].retired
        wait_lost(verifier, borrowed)
        fresh = instance(namespace, clock, instances, channels).reference()
        try:
            assert fresh.acquire(noop, 15)['generation'] == right['generation']
            assert len(instances.read_text().splitlines()) == 1
        finally:
            fresh.close()
    finally:
        other.close()
        first.close()
        second.close()
        if verifier is not None:
            verifier.close()
    assert owner.retired and all(channel.retired for channel in channels)


def test_actual_pool_owner_loss_never_rearms_old_reference_or_imports_old_idle(tmp_path):
    namespace, clock, instances = setup(tmp_path)
    channels = []
    owner = instance(namespace, clock, instances, channels).reference()
    borrower = instance(namespace, clock, instances, channels).reference()
    replacement = None
    try:
        with pytest.raises(AgentControlBusy):
            owner.acquire(noop, 15)
        clock.write_text('60', encoding='utf-8')
        old = owner.acquire(noop, 3)
        assert borrower.acquire(noop, 15)['generation'] == old['generation']
        owner.close()
        with pytest.raises(AgentTaskError):
            borrower.acquire(noop, 3)
        with pytest.raises(AgentTaskError):
            borrower.acquire(noop, 3)
        assert len(channels) == 2 and all(channel.retired for channel in channels)
        replacement = instance(namespace, clock, instances, channels).reference()
        with pytest.raises(AgentControlBusy):
            replacement.acquire(noop, 15)
        clock.write_text('120', encoding='utf-8')
        assert replacement.acquire(noop, 3)['generation'] != old['generation']
        assert len(instances.read_text().splitlines()) == 2
    finally:
        borrower.close()
        owner.close()
        if replacement is not None:
            replacement.close()
    assert all(channel.retired for channel in channels)


def test_actual_pool_caller_cancellation_reaps_late_token_without_closing_shared_process(tmp_path):
    namespace, clock, instances = setup(tmp_path)
    channels = []
    shared = instance(namespace, clock, instances, channels)
    first, second = shared.reference(), shared.reference()
    cancelled = threading.Event()
    gate = tmp_path / 'acquire-gate'
    verifier = None

    def check():
        if cancelled.is_set():
            raise CancelledError()

    try:
        with pytest.raises(AgentControlBusy):
            second.acquire(noop, 15)
        clock.write_text('60', encoding='utf-8')
        original = second.acquire(noop, 3)
        gate.write_text('block', encoding='utf-8')
        with ThreadPoolExecutor(max_workers=1) as executor:
            waiting = executor.submit(first.acquire, check, 3)
            wait_file(tmp_path / 'acquire-entered')
            cancelled.set()
            with pytest.raises(CancelledError):
                waiting.result(timeout=1)
        assert not channels[0].retired
        gate.unlink()
        wait_file(tmp_path / 'releases.txt')
        assert second.acquire(noop, 3)['generation'] == original['generation']
        verifier = create(namespace, clock, instances)
        verifier.request('bootstrap', {}, timeout=15)
        assert verifier.request('check', original, timeout=3)['status'] == 'ok'
        assert len(instances.read_text().splitlines()) == 1 and len(channels) == 1
    finally:
        gate.unlink(missing_ok=True)
        first.close()
        second.close()
        if verifier is not None:
            verifier.close()
    assert shared.retired and channels[0].retired
