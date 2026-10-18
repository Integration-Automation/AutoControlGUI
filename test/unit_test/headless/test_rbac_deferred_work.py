"""Delayed work uses its registrant's authority, including revocation checks."""
import json
import threading
from dataclasses import dataclass
from typing import Callable

import pytest

from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, authorization_scope, current_authorization, resolve_token,
)
from je_auto_control.utils.rbac.users import Role, UserStore
from je_auto_control.utils.run_history.history_store import HistoryStore, STATUS_ERROR

KINDS = ("interval", "cron", "trigger", "hotkey", "watchdog")
ADMIN = AuthorizationContext("worker-admin", Role.ADMIN)
OPERATOR = AuthorizationContext("registrant", Role.OPERATOR)


@dataclass
class Work:
    register: Callable[[], object]
    fire: Callable[[], object]


@pytest.fixture
def actions(tmp_path, monkeypatch):
    path = tmp_path / "actions.json"
    path.write_text(json.dumps([["AC_sign_action_file"]]), encoding="utf-8")
    calls = []
    monkeypatch.setitem(executor.event_dict, "AC_sign_action_file", lambda: calls.append(current_authorization()))
    return path, calls


@pytest.fixture
def history(monkeypatch):
    from je_auto_control.utils.hotkey import hotkey_daemon
    from je_auto_control.utils.scheduler import scheduler
    from je_auto_control.utils.triggers import trigger_engine
    store = HistoryStore()
    for module in (hotkey_daemon, scheduler, trigger_engine):
        monkeypatch.setattr(module, "default_history_store", store)
        monkeypatch.setattr(module, "capture_error_snapshot", lambda *_args: None)
    yield store
    store.close()


def _work(kind, path):
    """Construct detectors outside the registration scope, with no native input."""
    if kind in ("interval", "cron"):
        from je_auto_control.utils.scheduler.scheduler import Scheduler
        scheduler = Scheduler()
        registered = []

        def register():
            if kind == "interval":
                job = scheduler.add_job(str(path), 60, repeat=False)
            else:
                job = scheduler.add_cron_job(str(path), "* * * * *", max_runs=1)
            registered.append(job)

        return Work(register, lambda: scheduler._fire(registered[0], 0, 0))
    if kind == "trigger":
        from je_auto_control.utils.triggers.trigger_engine import FilePathTrigger, TriggerEngine
        engine = TriggerEngine()
        trigger = FilePathTrigger(trigger_id="t", script_path=str(path))
        return Work(lambda: engine.add(trigger), lambda: engine._fire(trigger, 0))
    if kind == "hotkey":
        from je_auto_control.utils.hotkey.hotkey_daemon import HotkeyDaemon
        daemon = HotkeyDaemon()
        return Work(lambda: daemon.bind("ctrl+alt+a", str(path), binding_id="h"),
                    lambda: daemon._fire_binding("h"))
    from je_auto_control.utils.watchdog.popup_watchdog import PopupWatchdog, WatchdogRule
    watchdog = PopupWatchdog()
    from je_auto_control.utils.json.json_file import read_executable_action_json
    rule = WatchdogRule("r", lambda: True,
                        lambda: executor.execute_action(read_executable_action_json(str(path))))
    return Work(lambda: watchdog.add_rule(rule), watchdog.check_once)


def _fire_on_worker(work, worker=ADMIN):
    outcomes = []
    errors = []

    def run():
        try:
            with authorization_scope(worker):
                outcomes.append(work.fire())
                assert current_authorization() is worker
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive(), "deferred work did not finish"
    assert not errors, errors
    return outcomes


@pytest.mark.parametrize("kind", KINDS)
def test_operator_cannot_gain_the_worker_threads_administrative_role(kind, actions, history):
    path, calls = actions
    work = _work(kind, path)
    with authorization_scope(OPERATOR):
        work.register()
    result = _fire_on_worker(work)
    assert calls == [], "the registrant's privileged command ran under another caller's authority"
    if kind == "watchdog":
        assert result == [0], "a denied command must not be recorded as a dismissed popup"
    if kind != "watchdog":
        assert history.list_runs()[0].status == STATUS_ERROR


@pytest.mark.parametrize("kind", KINDS)
def test_admin_registration_keeps_its_identity_on_an_unprivileged_worker(kind, actions, history):
    path, calls = actions
    work = _work(kind, path)
    owner = AuthorizationContext("owner-admin", Role.ADMIN)
    with authorization_scope(owner):
        work.register()
    _fire_on_worker(work, worker=OPERATOR)
    assert calls == [owner]


@pytest.mark.parametrize("kind", KINDS)
def test_work_registered_without_rbac_clears_ambient_worker_authority(kind, actions, history):
    path, calls = actions
    work = _work(kind, path)
    with authorization_scope(None):
        work.register()
    _fire_on_worker(work, worker=OPERATOR)
    assert calls == [None]


@pytest.mark.parametrize("change", ["remove", "viewer", "corrupt"])
@pytest.mark.parametrize("kind", KINDS)
def test_revoked_or_downgraded_registrants_cannot_execute(kind, change, actions, history, tmp_path):
    path, calls = actions
    store = UserStore(tmp_path / "users.json")
    token = store.add_user(user_id="owner", display_name="Owner", role=Role.ADMIN)
    owner = resolve_token(store, token)
    assert owner is not None
    work = _work(kind, path)
    with authorization_scope(owner):
        work.register()
    # A separately opened store stands in for the administration process.
    other = UserStore(store.path)
    if change == "remove":
        other.remove_user("owner")
    elif change == "viewer":
        other.set_role("owner", Role.VIEWER)
    else:
        store.path.write_text("corrupted", encoding="utf-8")
    _fire_on_worker(work)
    assert calls == []
    if kind != "watchdog":
        assert history.list_runs()[0].status == STATUS_ERROR


@pytest.mark.parametrize("kind", KINDS)
def test_downgrade_to_operator_blocks_privileged_commands_but_runs_safe_work(
        kind, actions, history, tmp_path, monkeypatch):
    path, calls = actions
    store = UserStore(tmp_path / "users.json")
    token = store.add_user(user_id="owner", display_name="Owner", role=Role.ADMIN)
    owner = resolve_token(store, token)
    work = _work(kind, path)
    with authorization_scope(owner):
        work.register()
    UserStore(store.path).set_role("owner", Role.OPERATOR)
    safe_calls = []
    monkeypatch.setitem(executor.event_dict, "AC_slugify", lambda text: safe_calls.append(current_authorization()))
    path.write_text(json.dumps([["AC_slugify", {"text": "safe"}], ["AC_sign_action_file"]]), encoding="utf-8")
    _fire_on_worker(work)
    assert calls == []
    assert [(call.user_id, call.role) for call in safe_calls] == [("owner", Role.OPERATOR)]


@pytest.mark.parametrize("kind", ("trigger", "watchdog"))
def test_shared_rule_objects_do_not_share_registration_authority(kind, actions, history):
    path, calls = actions
    if kind == "trigger":
        from je_auto_control.utils.triggers.trigger_engine import FilePathTrigger, TriggerEngine
        first, second = TriggerEngine(), TriggerEngine()
        shared = FilePathTrigger(trigger_id="shared", script_path=str(path))
        def register_first():
            return first.add(shared)
        def register_second():
            return second.add(shared)
        def fire_first():
            return first._fire(shared, 0)
        def fire_second():
            return second._fire(shared, 0)
    else:
        from je_auto_control.utils.watchdog.popup_watchdog import PopupWatchdog, WatchdogRule
        first, second = PopupWatchdog(), PopupWatchdog()
        shared = WatchdogRule("shared", lambda: True,
                              lambda: executor.execute_action([["AC_sign_action_file"]]))
        def register_first():
            return first.add_rule(shared)
        def register_second():
            return second.add_rule(shared)
        fire_first, fire_second = first.check_once, second.check_once
    with authorization_scope(OPERATOR):
        register_first()
    with authorization_scope(ADMIN):
        register_second()
    fire_first()
    assert calls == []
    fire_second()
    assert calls == [ADMIN]


@pytest.mark.parametrize("kind", KINDS)
def test_live_daemon_dispatch_preserves_identity_and_opens_a_fresh_variable_scope(
        kind, actions, history, monkeypatch):
    from je_auto_control.utils.script_vars.execution import current_scope

    path, _ = actions
    path.write_text(json.dumps([["AC_slugify", {"text": "tick"}]]), encoding="utf-8")
    reached = threading.Event()
    seen = []

    def step(text):
        seen.append((current_authorization(), current_scope()))
        reached.set()

    monkeypatch.setitem(executor.event_dict, "AC_slugify", step)
    with authorization_scope(OPERATOR):
        if kind in ("interval", "cron"):
            from je_auto_control.utils.scheduler.scheduler import Scheduler
            daemon = Scheduler(tick_seconds=0.1)
            if kind == "cron":
                job = daemon.add_cron_job(str(path), "* * * * *", max_runs=1)
                job.next_run_ts = 0
            else:
                daemon.add_job(str(path), 0.1, repeat=False)
        elif kind == "trigger":
            from je_auto_control.utils.triggers.trigger_engine import _TriggerBase, TriggerEngine

            class ReadyTrigger(_TriggerBase):
                def is_fired(self):
                    return True

            daemon = TriggerEngine(tick_seconds=0.01)
            daemon.add(ReadyTrigger("tick", str(path), cooldown_seconds=0))
        elif kind == "hotkey":
            from je_auto_control.utils.hotkey import backends
            from je_auto_control.utils.hotkey.hotkey_daemon import HotkeyDaemon

            class FakeNativeBackend:
                name = "test"

                def run_forever(self, context):
                    context.fire("tick")
                    context.stop_event.wait(5)

            monkeypatch.setattr(backends, "get_backend", lambda: FakeNativeBackend())
            daemon = HotkeyDaemon()
            daemon.bind("ctrl+alt+a", str(path), binding_id="tick")
        else:
            from je_auto_control.utils.watchdog.popup_watchdog import PopupWatchdog, WatchdogRule
            from je_auto_control.utils.json.json_file import read_executable_action_json
            daemon = PopupWatchdog(poll_interval_s=0.01)
            daemon.add_rule(WatchdogRule("tick", lambda: not reached.is_set(),
                                        lambda: executor.execute_action(read_executable_action_json(str(path)))))
    try:
        with authorization_scope(ADMIN):
            daemon.start()
        assert reached.wait(5), f"{kind} did not dispatch"
    finally:
        daemon.stop(timeout=5)
    assert len(seen) == 1
    assert seen[0][0] == OPERATOR
    assert seen[0][1] is not None
    assert current_authorization() is None
