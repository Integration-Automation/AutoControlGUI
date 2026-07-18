"""Round-3 net audit: background poll loops must survive per-tick failures.

The scheduler, ACME renewal, screen observer, and popup watchdog each own a
single daemon thread. Any escaping exception is a poison pill that stops *all*
work the thread drives. These tests pin the containment at each loop's edge.
"""
import sqlite3
import time

import je_auto_control.wrapper.auto_control_image as image_mod
from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, AutoControlCantFindKeyException,
    AutoControlKeyboardException, AutoControlScreenException,
    ImageNotFoundException,
)
from je_auto_control.utils.observer.observer import (
    ScreenObserver, image_predicate,
)
from je_auto_control.utils.scheduler import scheduler as sch
from je_auto_control.utils.tls_acme import renewal
from je_auto_control.utils.watchdog.popup_watchdog import (
    PopupWatchdog, WatchdogRule,
)


# --- finding 4: scheduler --------------------------------------------------

def test_tick_survives_history_db_error(monkeypatch):
    """A sqlite3.Error from start_run (outside _fire's own except) is contained."""
    class BoomHistory:
        def start_run(self, *args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

        def finish_run(self, *args, **kwargs):
            return True

    monkeypatch.setattr(sch, "default_history_store", BoomHistory())
    monkeypatch.setattr(sch, "capture_error_snapshot", lambda run_id: None)
    monkeypatch.setattr(sch, "read_action_json", lambda path: [])

    scheduler = sch.Scheduler(executor=lambda actions: None, tick_seconds=0.05)
    job = scheduler.add_job("s.json", interval_seconds=0.1)
    job.next_run_ts = 0.0  # force it due

    scheduler._tick_once()  # must not raise despite start_run exploding


def test_tick_survives_snapshot_error(monkeypatch):
    """An AutoControlScreenException from capture_error_snapshot (in _fire's
    finally) must not escape the tick."""
    class OkHistory:
        def start_run(self, *args, **kwargs):
            return 1

        def finish_run(self, *args, **kwargs):
            return True

    monkeypatch.setattr(sch, "default_history_store", OkHistory())

    def boom_snapshot(run_id):
        raise AutoControlScreenException("no display")

    monkeypatch.setattr(sch, "capture_error_snapshot", boom_snapshot)
    monkeypatch.setattr(sch, "read_action_json", lambda path: [])

    def failing_exec(actions):
        raise AutoControlActionException("bad action")

    scheduler = sch.Scheduler(executor=failing_exec, tick_seconds=0.05)
    job = scheduler.add_job("s.json", interval_seconds=0.1)
    job.next_run_ts = 0.0

    scheduler._tick_once()  # must not raise


def test_scheduler_thread_stays_alive_on_db_error(monkeypatch):
    class BoomHistory:
        def start_run(self, *args, **kwargs):
            raise sqlite3.OperationalError("locked")

        def finish_run(self, *args, **kwargs):
            return True

    monkeypatch.setattr(sch, "default_history_store", BoomHistory())
    monkeypatch.setattr(sch, "capture_error_snapshot", lambda run_id: None)
    monkeypatch.setattr(sch, "read_action_json", lambda path: [])

    scheduler = sch.Scheduler(executor=lambda actions: None, tick_seconds=0.05)
    scheduler.add_job("s.json", interval_seconds=0.05)
    scheduler.start()
    time.sleep(0.3)
    try:
        assert scheduler._thread.is_alive()
    finally:
        scheduler.stop()


# --- finding 5: ACME renewal ----------------------------------------------

def test_raising_on_failure_hook_does_not_escape_tick(tmp_path):
    cert = tmp_path / "missing.pem"  # missing -> renewal_due True

    def bad_renew():
        raise RuntimeError("certbot failed")

    def bad_hook(_error):
        raise ValueError("alerting is down")

    scheduler = renewal.RenewalScheduler(
        cert, bad_renew, on_failure=bad_hook, check_interval_s=999)

    assert scheduler.tick() is True  # hook raises but must not propagate


def test_renewal_loop_survives_raising_tick(monkeypatch, tmp_path):
    cert = tmp_path / "missing.pem"
    scheduler = renewal.RenewalScheduler(
        cert, lambda: None, check_interval_s=0.05)

    def boom_tick():
        raise RuntimeError("kaboom")

    monkeypatch.setattr(scheduler, "tick", boom_tick)
    scheduler.start()
    time.sleep(0.2)
    try:
        assert scheduler.is_running  # thread survived the raising tick
    finally:
        scheduler.stop()


# --- finding 6: screen observer -------------------------------------------

def test_image_predicate_absent_does_not_kill_poll_once(monkeypatch):
    def raise_not_found(*_args, **_kwargs):
        raise ImageNotFoundException("absent")

    monkeypatch.setattr(image_mod, "locate_image_center", raise_not_found)
    observer = ScreenObserver()
    observer.add("img", image_predicate("x.png"), lambda ev, val: None)

    assert observer.poll_once() == []  # contained, no event, no raise


def test_handler_raising_framework_exc_is_contained():
    observer = ScreenObserver()

    def handler(_event, _value):
        raise AutoControlKeyboardException("bad key")

    observer.add("appear", lambda: True, handler)
    events = observer.poll_once()  # handler raises but is contained
    assert len(events) == 1  # transition still recorded


# --- finding 7: popup watchdog --------------------------------------------

def test_action_raising_keyboard_exc_does_not_kill_check():
    watchdog = PopupWatchdog()

    def action():
        raise AutoControlCantFindKeyException("no such key")

    watchdog.add_rule(
        WatchdogRule(name="r", matcher=lambda: True, action=action))

    assert watchdog.check_once() == 0  # rule error contained, no raise
