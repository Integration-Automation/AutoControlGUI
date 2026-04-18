"""Tests for the Scheduler headless module."""
import time

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


def test_job_fires_and_updates_runs(monkeypatch):
    executed = []
    sched = Scheduler(
        executor=lambda actions: executed.append(actions),
        tick_seconds=0.1,
    )
    monkeypatch.setattr(
        "je_auto_control.utils.scheduler.scheduler.read_action_json",
        lambda path: [["AC_noop"]],
    )
    job = sched.add_job("fake.json", interval_seconds=0.1, repeat=False)
    sched.start()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and sched.list_jobs():
            time.sleep(0.05)
    finally:
        sched.stop(timeout=1.0)
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
        "je_auto_control.utils.scheduler.scheduler.read_action_json",
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
