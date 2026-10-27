"""Shared source lifetime is independent of individual task cancellation and late lease replies."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
import threading
import time

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.presence_protocol import PresenceProtocol
from .presence_test_support import Source


class Channel:
    def __init__(self, ready=True):
        self.source = Source()
        self.source.start()
        if ready:
            self.source.advance(60)
        self.protocol = PresenceProtocol(self.source)
        self.calls, self.threads = [], set()
        self.retired = False
        self.entered, self.allow = threading.Event(), threading.Event()
        self.allow.set()
        self.hang, self.fail = False, False
        self.sequence = 1

    def request(self, operation, body, *, timeout, check):
        self.calls.append((operation, dict(body)))
        self.threads.add(threading.get_ident())
        check()
        if operation == 'bootstrap':
            return {'ready': True, 'generation': self.protocol.generation}
        if operation == 'acquire':
            self.entered.set()
            while not self.allow.wait(0.01):
                check()
        if self.fail:
            raise AgentTaskError('source protocol failed')
        value = self.protocol.request({'request_id': self.sequence, 'operation': operation, 'body': body})
        self.sequence += 1
        return value

    def close(self):
        self.retired = True
        self.source.close()


def pool(factory):
    from je_auto_control.utils.agent_runtime.presence_pool import PresencePool
    return PresencePool(channel_factory=factory)


def noop():
    return None


def test_pool_reference_status_and_unstarted_close_do_not_create_any_helper():
    calls = []
    instance = pool(lambda _argv: calls.append('created'))
    first, second = instance.reference(), instance.reference()
    assert instance.status()['state'] == 'not_started' and not calls
    first.close()
    assert not calls
    second.close()
    assert instance.retired and not calls


def test_two_references_share_one_broker_and_closing_one_keeps_the_other_lease():
    channels = []

    def create(argv):
        assert argv[-2:] == ['-m', 'je_auto_control.utils.agent_runtime.presence_broker']
        value = Channel()
        channels.append(value)
        return value

    instance = pool(create)
    first, second = instance.reference(), instance.reference()
    try:
        left, right = first.acquire(noop, 2), second.acquire(noop, 2)
        assert left['generation'] == right['generation'] and len(channels) == 1
        first.close()
        another = second.acquire(noop, 2)
        assert another['generation'] == right['generation'] and not channels[0].retired
        assert channels[0].source.released.wait(1)
        assert len(channels[0].threads) == 1
        with pytest.raises(AgentTaskError):
            second.release(left)
    finally:
        first.close()
        second.close()
    assert channels[0].retired and instance.retired


def test_busy_acquisition_does_not_retire_or_restart_the_source():
    channel = Channel(ready=False)
    instance = pool(lambda _argv: channel)
    reference = instance.reference()
    try:
        with pytest.raises(AgentControlBusy):
            reference.acquire(noop, 2)
        assert not channel.retired
        channel.source.advance(60)
        assert reference.acquire(noop, 2)['generation'] == channel.protocol.generation
        assert [name for name, _body in channel.calls].count('bootstrap') == 1
    finally:
        reference.close()


def test_cancelled_waiter_cannot_cancel_a_different_references_shared_rpc_or_late_lease():
    channel = Channel()
    channel.allow.clear()
    instance = pool(lambda _argv: channel)
    first, second = instance.reference(), instance.reference()
    cancelled = threading.Event()

    def check():
        if cancelled.is_set():
            raise CancelledError()

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            waiting = executor.submit(first.acquire, check, 2)
            assert channel.entered.wait(1)
            cancelled.set()
            with pytest.raises(CancelledError):
                waiting.result(timeout=1)
            assert not channel.retired
            channel.allow.set()
        token = second.acquire(noop, 2)
        assert channel.source.released.wait(1)
        assert token['generation'] == channel.protocol.generation and not channel.retired
    finally:
        channel.allow.set()
        first.close()
        second.close()


def test_individual_wait_deadline_abandons_late_grant_without_killing_shared_source():
    channel = Channel()
    channel.allow.clear()
    instance = pool(lambda _argv: channel)
    first, second = instance.reference(), instance.reference()
    try:
        started = time.monotonic()
        with pytest.raises(AgentTaskError, match='deadline'):
            first.acquire(noop, 0.1)
        assert time.monotonic() - started < 0.5 and not channel.retired
        channel.allow.set()
        assert second.acquire(noop, 2)['generation'] == channel.protocol.generation
        assert channel.source.released.wait(1)
    finally:
        channel.allow.set()
        first.close()
        second.close()


def test_last_close_cancels_shared_lifetime_and_proves_owned_thread_retirement():
    channel = Channel()
    channel.allow.clear()
    instance = pool(lambda _argv: channel)
    reference = instance.reference()
    with ThreadPoolExecutor(max_workers=1) as executor:
        waiting = executor.submit(reference.acquire, noop, 10)
        assert channel.entered.wait(1)
        started = time.monotonic()
        reference.close()
        assert time.monotonic() - started < 3 and channel.retired and instance.retired
        with pytest.raises(AgentTaskError):
            waiting.result(timeout=1)
    with pytest.raises(AgentTaskError):
        reference.acquire(noop, 2)


def test_late_helper_construction_after_last_close_never_receives_a_bootstrap():
    entered, allow = threading.Event(), threading.Event()
    channel = Channel()

    def create(_argv):
        entered.set()
        assert allow.wait(2)
        return channel

    instance = pool(create)
    reference = instance.reference()
    with ThreadPoolExecutor(max_workers=2) as executor:
        acquiring = executor.submit(reference.acquire, noop, 10)
        assert entered.wait(1)
        closing = executor.submit(reference.close)
        deadline = time.monotonic() + 1
        while not reference.closed and time.monotonic() < deadline:
            time.sleep(0.001)
        assert reference.closed
        allow.set()
        closing.result(timeout=3)
        with pytest.raises(AgentTaskError):
            acquiring.result(timeout=1)
    assert channel.retired and not channel.calls and instance.retired


def test_fatal_source_rpc_does_not_rearm_an_existing_reference():
    channel = Channel()
    channel.fail = True
    calls = []

    def create(_argv):
        calls.append('start')
        return channel

    instance = pool(create)
    first, second = instance.reference(), instance.reference()
    try:
        with pytest.raises(AgentTaskError):
            first.acquire(noop, 2)
        with pytest.raises(AgentTaskError):
            second.acquire(noop, 2)
        assert calls == ['start']
    finally:
        first.close()
        second.close()


def test_failed_retirement_keeps_process_owned_and_allows_only_explicit_cleanup_retry():
    channel = Channel()
    original = channel.close
    fail = [True]

    def close():
        if fail[0]:
            raise AgentTaskError('owned test process retirement is unknown')
        original()

    channel.close = close
    instance = pool(lambda _argv: channel)
    reference = instance.reference()
    reference.acquire(noop, 2)
    with pytest.raises(AgentTaskError):
        reference.close()
    assert not instance.retired and not channel.retired
    fail[0] = False
    reference.close()
    assert instance.retired and channel.retired
    with pytest.raises(AgentTaskError):
        reference.acquire(noop, 2)


def test_failed_owner_thread_start_never_constructs_a_source_or_leaves_an_unjoinable_owner(monkeypatch):
    calls = []
    instance = pool(lambda _argv: calls.append('created'))
    reference = instance.reference()

    def fail_start(_thread):
        raise RuntimeError('thread admission failed')

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, 'start', fail_start)
        with pytest.raises(AgentTaskError, match='thread'):
            reference.acquire(noop, 2)
    reference.close()
    assert instance.retired and not calls
    with pytest.raises(AgentTaskError):
        reference.acquire(noop, 2)


def test_failed_cleanup_thread_start_keeps_the_original_process_owned_for_retry(monkeypatch):
    channel = Channel()
    original = channel.close

    def fail_close():
        raise AgentTaskError('owned retirement is unproven')

    channel.close = fail_close
    instance = pool(lambda _argv: channel)
    reference = instance.reference()
    reference.acquire(noop, 2)
    with pytest.raises(AgentTaskError):
        reference.close()

    def fail_start(_thread):
        raise RuntimeError('cleanup thread admission failed')

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, 'start', fail_start)
        with pytest.raises(AgentTaskError, match='thread'):
            reference.close()
    assert not instance.retired and not channel.retired
    channel.close = original
    reference.close()
    assert instance.retired and channel.retired


def registry(monkeypatch, channels):
    from je_auto_control.utils.agent_runtime import presence_pool
    constructor = presence_pool.PresencePool
    pools = []

    def create():
        channel = channels[len(pools)]
        instance = constructor(channel_factory=lambda _argv: channel)
        pools.append(instance)
        return instance

    monkeypatch.setattr(presence_pool, '_SHARED', presence_pool._Registry())
    monkeypatch.setattr(presence_pool, 'PresencePool', create)
    return presence_pool, pools


def test_shared_registry_is_passive_and_replaces_only_a_retired_closed_lifetime(monkeypatch):
    channels = [Channel(), Channel()]
    module, pools = registry(monkeypatch, channels)
    assert module.shared_status()['state'] == 'not_started' and not pools
    first, second = module.shared_reference(), module.shared_reference()
    try:
        assert len(pools) == 1 and not channels[0].calls
        old = first.acquire(noop, 2)
        first.close()
        assert second.acquire(noop, 2)['generation'] == old['generation']
        assert module.shared_status()['references'] == 1
    finally:
        first.close()
        second.close()
    fresh = module.shared_reference()
    try:
        assert len(pools) == 2 and pools[0].retired
        assert fresh.acquire(noop, 2)['generation'] != old['generation']
        first.close()
        second.close()
        assert not channels[1].retired
        with pytest.raises(AgentTaskError):
            second.acquire(noop, 2)
    finally:
        fresh.close()


def test_shared_registry_can_replace_failed_retired_source_but_old_reference_never_rearms(monkeypatch):
    channels = [Channel(), Channel()]
    module, pools = registry(monkeypatch, channels)
    old = module.shared_reference()
    fresh = None
    try:
        previous = old.acquire(noop, 2)
        channels[0].fail = True
        with pytest.raises(AgentTaskError):
            old.acquire(noop, 2)
        deadline = time.monotonic() + 1
        while not pools[0].retired and time.monotonic() < deadline:
            time.sleep(0.001)
        assert pools[0].retired
        fresh = module.shared_reference()
        assert fresh.acquire(noop, 2)['generation'] != previous['generation']
        old.close()
        assert not channels[1].retired
        with pytest.raises(AgentTaskError):
            old.acquire(noop, 2)
    finally:
        old.close()
        if fresh is not None:
            fresh.close()


def test_shared_registry_refuses_replacement_until_actual_process_retirement(monkeypatch):
    channels = [Channel(), Channel()]
    module, pools = registry(monkeypatch, channels)
    old = module.shared_reference()
    original = channels[0].close

    def fail_close():
        raise AgentTaskError('retained process is not retired')

    channels[0].close = fail_close
    old.acquire(noop, 2)
    try:
        with pytest.raises(AgentTaskError):
            old.close()
        with pytest.raises(AgentTaskError):
            module.shared_reference()
        assert len(pools) == 1 and not channels[0].retired and not channels[1].calls
    finally:
        channels[0].close = original
        old.close()
    fresh = module.shared_reference()
    try:
        assert len(pools) == 2 and pools[0].retired
    finally:
        fresh.close()
