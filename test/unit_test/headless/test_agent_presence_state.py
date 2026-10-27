"""Physical source state uses deterministic clocks only; no native observer is started."""
from concurrent.futures import ThreadPoolExecutor
import json
import re
import threading

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError


class Clock:
    def __init__(self):
        self.value = 0.0
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.value


def source(clock):
    from je_auto_control.utils.agent_runtime.presence_state import PresenceState
    return PresenceState(clock)


def advance(state, clock, seconds, *, interactive=True, held=False):
    end = clock.value + seconds
    while clock.value < end:
        clock.value = min(end, clock.value + 0.125)
        state.refresh(interactive, held)


def ready():
    clock = Clock()
    state = source(clock)
    state.refresh(True, False)
    advance(state, clock, 60)
    return state, clock, state.acquire()


def test_construction_is_inert_and_unstarted_source_cannot_acquire():
    clock = Clock()
    state = source(clock)
    assert clock.calls == 0
    assert state.inspect()['state'] == 'not_started'
    with pytest.raises(AgentControlBusy):
        state.acquire()


def test_fresh_source_observes_exact_sixty_seconds_and_ignores_old_system_uptime():
    clock = Clock()
    clock.value = 10000
    state = source(clock)
    state.refresh(True, False)
    advance(state, clock, 59)
    with pytest.raises(AgentControlBusy):
        state.acquire()
    advance(state, clock, 1)
    lease = state.acquire()
    assert set(lease) == {'generation', 'lease_id'}
    assert all(re.fullmatch('[0-9a-f]{32}', value) for value in lease.values())
    assert state.check(**lease)['idle_seconds'] == 60
    assert state.inspect()['native_evidence'] == 'not_recorded'


def test_physical_takeover_invalidates_old_lease_permanently():
    state, clock, lease = ready()
    state.physical()
    state.physical()
    with pytest.raises(AgentTaskError, match='resume'):
        state.check(**lease)
    advance(state, clock, 60)
    with pytest.raises(AgentTaskError, match='resume'):
        state.check(**lease)
    assert state.acquire() != lease


def test_held_input_blocks_acquisition_but_not_its_current_owned_lease():
    state, _clock, lease = ready()
    state.refresh(True, True)
    with pytest.raises(AgentControlBusy):
        state.acquire()
    assert state.check(**lease)['held'] is True
    state.refresh(True, False)
    assert state.check(**lease)['state'] == 'monitoring'


def test_lock_unlock_requires_a_new_idle_period_and_never_rearms_old_lease():
    state, clock, lease = ready()
    state.refresh(False, False)
    with pytest.raises(AgentTaskError, match='resume'):
        state.check(**lease)
    advance(state, clock, 60, interactive=False)
    state.refresh(True, False)
    assert state.inspect()['idle_seconds'] == 0
    with pytest.raises(AgentControlBusy):
        state.acquire()
    advance(state, clock, 60)
    with pytest.raises(AgentTaskError, match='resume'):
        state.check(**lease)
    assert state.acquire() != lease


@pytest.mark.parametrize('read_stale_first', [False, True])
def test_monitoring_gap_requires_fresh_idle_and_irrevocably_fences_old_lease(read_stale_first):
    state, clock, lease = ready()
    clock.value += 0.5
    if read_stale_first:
        assert state.inspect()['state'] == 'unavailable'
    state.refresh(True, False)
    assert state.inspect()['idle_seconds'] == 0
    with pytest.raises(AgentTaskError, match='resume'):
        state.check(**lease)
    with pytest.raises(AgentControlBusy):
        state.acquire()
    advance(state, clock, 60)
    assert state.acquire() != lease


@pytest.mark.parametrize('invalid', [True, None, 'clock', float('nan'), float('inf'), -1.0, 59.0,
                                  pytest.param(10 ** 1000, id='overflow')])
def test_invalid_or_regressing_clock_cannot_return_authority(invalid):
    state, clock, lease = ready()
    clock.value = invalid
    assert state.inspect()['state'] == 'unavailable'
    clock.value = 61
    with pytest.raises(AgentTaskError):
        state.refresh(True, False)
    with pytest.raises(AgentTaskError):
        state.check(**lease)


def test_native_failure_and_close_cannot_restart_the_same_source():
    state, _clock, lease = ready()
    state.fail()
    state.close()
    assert state.inspect()['state'] == 'unavailable'
    with pytest.raises(AgentTaskError):
        state.refresh(True, False)
    with pytest.raises(AgentTaskError):
        state.check(**lease)
    state.release(**lease)


def test_generation_and_released_tokens_cannot_select_another_lease():
    state, _clock, lease = ready()
    other, _other_clock, foreign = ready()
    with pytest.raises(AgentTaskError):
        other.check(**lease)
    assert other.check(**foreign)['state'] == 'monitoring'
    state.release(**lease)
    with pytest.raises(AgentTaskError):
        state.check(**lease)
    assert state.acquire() != lease


def test_lease_capacity_is_atomic_and_only_explicit_release_reclaims_a_slot():
    state, _clock, first = ready()
    barrier = threading.Barrier(17)

    def claim(_index):
        barrier.wait(timeout=2)
        try:
            return state.acquire()
        except AgentControlBusy:
            return None

    with ThreadPoolExecutor(max_workers=17) as executor:
        results = list(executor.map(claim, range(17)))
    assert sum(value is not None for value in results) == 15
    assert results.count(None) == 2
    state.release(**first)
    assert state.acquire() != first


def test_projection_contains_only_presence_metadata_and_is_detached():
    state, _clock, lease = ready()
    projection = state.check(**lease)
    assert set(projection) == {'state', 'idle_seconds', 'interactive', 'held', 'generation',
                               'revision', 'native_evidence'}
    json.dumps(projection, allow_nan=False)
    projection['state'] = 'forged'
    assert state.inspect()['state'] == 'monitoring'


@pytest.mark.parametrize('interactive,held', [(1, False), (True, 0), ('unlocked', False)])
def test_native_state_flags_require_actual_booleans(interactive, held):
    state = source(Clock())
    with pytest.raises(AgentTaskError):
        state.refresh(interactive, held)
    assert state.inspect()['state'] == 'unavailable'
