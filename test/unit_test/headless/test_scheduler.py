"""Tests for the Scheduler headless module."""
import time

import pytest

from je_auto_control.utils.scheduler.scheduler import Scheduler


def test_add_and_remove_job():
    calls = []
    sched = Scheduler(executor=lambda actions: calls.append(actions))
    job = sched.add_job("script.json", interval_seconds=5.0)
    assert job.script_path == "script.json"
    assert len(sched.list_jobs()) == 1
    assert sched.remove_job(job.job_id) is True
    assert sched.list_jobs() == []


def test_set_enabled_toggles_flag():
    sched = Scheduler(executor=lambda actions: None)
    job = sched.add_job("s.json", 10.0)
    assert sched.set_enabled(job.job_id, False) is True
    assert sched.list_jobs()[0].enabled is False
    assert sched.set_enabled("no-such-job", True) is False


@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_job_fires_and_updates_runs(monkeypatch):
    executed = []
    sched = Scheduler(
        executor=lambda actions: executed.append(actions),
        tick_seconds=0.1,
    )
    monkeypatch.setattr(
        "je_auto_control.utils.scheduler.scheduler.read_executable_action_json",
        lambda path: [["AC_noop"]],
    )
    job = sched.add_job("fake.json", interval_seconds=0.1, repeat=False)
    sched.start()
    try:
        # 8s budget so a sluggish Windows-2022 CI runner has headroom
        # past the 100 ms tick — the previous 2s timed out under load.
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline and sched.list_jobs():
            time.sleep(0.05)
    finally:
        sched.stop(timeout=2.0)
    assert executed, "executor should have been called at least once"
    # Non-repeating job is removed after firing.
    assert all(j.job_id != job.job_id for j in sched.list_jobs())


def test_max_runs_cap(monkeypatch):
    executed = []
    sched = Scheduler(
        executor=lambda actions: executed.append(1),
        tick_seconds=0.05,
    )
    monkeypatch.setattr(
        "je_auto_control.utils.scheduler.scheduler.read_executable_action_json",
        lambda path: [["AC_noop"]],
    )
    sched.add_job("fake.json", interval_seconds=0.1,
                  repeat=True, max_runs=2)
    sched.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and sched.list_jobs():
            time.sleep(0.05)
    finally:
        sched.stop(timeout=1.0)
    assert len(executed) == 2


class _NullHistory:
    """Run-history store that records nothing."""

    def start_run(self, *_args, **_kwargs):
        return 1

    def finish_run(self, *_args, **_kwargs):
        return None


def test_a_job_still_running_is_not_started_again(monkeypatch):
    """A job is rescheduled only when it finishes, so it looks due until then.

    One loop cannot overlap itself, but two can: the new run after a stop()
    whose join timed out inside a long job used to see that job as due and
    start it a second time while the first was still executing.
    """
    import threading

    from je_auto_control.utils.scheduler import scheduler as scheduler_mod
    monkeypatch.setattr(scheduler_mod, "default_history_store", _NullHistory())
    monkeypatch.setattr(scheduler_mod, "read_executable_action_json",
                        lambda path: [["AC_noop"]])
    entered, release = threading.Event(), threading.Event()
    calls = []

    def executor(actions):
        calls.append(actions)
        if len(calls) == 1:
            entered.set()
            release.wait(5.0)

    sched = Scheduler(executor=executor)
    sched.add_job("fake.json", interval_seconds=0.1, repeat=True)
    time.sleep(0.15)                      # let the job fall due
    first = threading.Thread(target=sched._tick_once, daemon=True)
    first.start()
    try:
        assert entered.wait(2.0), "the first loop never started the job"
        sched._tick_once()                # a second loop, same instant
        assert len(calls) == 1, "the job was started again while running"
    finally:
        release.set()
        first.join(2.0)
    assert not first.is_alive()
    # Finished and rescheduled: it may run again once it is due.
    time.sleep(0.15)
    sched._tick_once()
    assert len(calls) == 2
