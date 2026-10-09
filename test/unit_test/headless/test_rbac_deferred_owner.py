"""Deferred work runs as whoever registered it, with the role they hold when it fires.

A scheduler job, a trigger, a hotkey binding, a webhook, an e-mail trigger
and a watchdog rule all fire on a daemon thread, outside the request that
registered them. They used to run with no identity, so an operator could
register a job whose action file held a privileged command and the executor
ran it unchecked.

Nothing here touches the real mouse, keyboard or screen: each engine is
fired by hand, the run history is a fake, and the privileged command is
replaced by a recorder.
"""
import json
import time

import pytest

from je_auto_control.utils.executor.action_executor import execute_action, executor
from je_auto_control.utils.hotkey import hotkey_daemon
from je_auto_control.utils.hotkey.hotkey_daemon import HotkeyDaemon
from je_auto_control.utils.rbac import (
    USERS_ENV, AuthorizationContext, AuthorizationError, DeferredOwner, Role,
    UserStore, authorization_scope, capture_owner, current_authorization,
    owner_scope, resolve_owner, resolve_token,
)
from je_auto_control.utils.run_history.run_outcome import run_counting_failures
from je_auto_control.utils.scheduler import scheduler as scheduler_module
from je_auto_control.utils.scheduler.scheduler import ScheduledJob, Scheduler
from je_auto_control.utils.triggers import email_trigger, trigger_engine, webhook_server
from je_auto_control.utils.triggers.email_trigger import EmailTriggerWatcher
from je_auto_control.utils.triggers.trigger_engine import TriggerEngine, WindowAppearsTrigger
from je_auto_control.utils.triggers.webhook_server import WebhookTriggerServer
from je_auto_control.utils.watchdog.popup_watchdog import PopupWatchdog, WatchdogRule

_SIGN = "AC_sign_action_file"
_PROBE = "AC_deferred_probe"
_ENGINES = ("scheduler", "trigger", "hotkey", "webhook", "email")


class _FakeHistory:
    """Stands in for the run-history database; keeps how each run finished."""

    def __init__(self):
        self.finished = []

    def start_run(self, *_args):
        return 1

    def finish_run(self, _run_id, status, error_text=None, artifact_path=None):
        self.finished.append((status, error_text))


@pytest.fixture(autouse=True)
def _no_ambient_rbac(monkeypatch):
    monkeypatch.delenv(USERS_ENV, raising=False)


@pytest.fixture
def history(monkeypatch):
    fake = _FakeHistory()
    for module in (scheduler_module, trigger_engine, hotkey_daemon, webhook_server,
                   email_trigger):
        monkeypatch.setattr(module, "default_history_store", fake)
        monkeypatch.setattr(module, "capture_error_snapshot", lambda _run_id: None)
    return fake


@pytest.fixture
def ran(monkeypatch):
    """Names of the commands that actually ran: the privileged one and a plain probe."""
    names = []
    monkeypatch.setitem(executor.event_dict, _SIGN,
                        lambda **_kwargs: names.append(_SIGN))
    monkeypatch.setitem(executor.event_dict, _PROBE, lambda: names.append(_PROBE))
    return names


@pytest.fixture
def users(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.tokens = {
        role: store.add_user(user_id=f"{role}-user", display_name=role, role=role)
        for role in Role.all()
    }
    return store


@pytest.fixture
def script(tmp_path):
    path = tmp_path / "job.json"
    path.write_text(json.dumps([[_PROBE], [_SIGN, {"path": "x"}]]), encoding="utf-8")
    return str(path)


def _as(users, role):
    """The scope a server puts a request of ``role``'s user in."""
    return authorization_scope(resolve_token(users, users.tokens[role]))


def _register(kind, script):
    """Register ``script`` with a fresh engine; return a callable that fires it once."""
    def run(actions, _payload=None):
        return execute_action(actions)

    if kind == "scheduler":
        engine = Scheduler(executor=run)
        job = engine.add_job(script, 60)
        return job, lambda: engine._fire(job, time.monotonic(), time.time())
    if kind == "trigger":
        engine = TriggerEngine(executor=run)
        trigger = engine.add(WindowAppearsTrigger("", script, title_substring="x"))
        return trigger, lambda: engine._fire(trigger, time.monotonic())
    if kind == "hotkey":
        daemon = HotkeyDaemon(executor=run)
        binding = daemon.bind("ctrl+alt+1", script)
        return binding, lambda: daemon._fire_binding(binding.binding_id)
    if kind == "webhook":
        server = WebhookTriggerServer(executor=run)
        hook = server.add("/hook", script)
        return hook, lambda: server.fire(hook, {})
    watcher = EmailTriggerWatcher(executor=run)
    mail = watcher.add("imap.invalid", "user", "pw", script)

    def fire():
        try:
            watcher._execute_with_history(mail, {})
        except Exception:  # noqa: BLE001  # reason: this watcher re-raises; the fake history holds the outcome
            pass
    return mail, fire


# --- the defect -------------------------------------------------------------

@pytest.mark.parametrize("kind", _ENGINES)
def test_an_operators_deferred_work_cannot_run_a_privileged_command(
        kind, users, script, history, ran):
    with _as(users, Role.OPERATOR):
        entry, fire = _register(kind, script)
    assert entry.owner == DeferredOwner("operator-user", Role.OPERATOR)
    assert current_authorization() is None
    fire()
    assert ran == [_PROBE], "the plain command runs, the privileged one is refused"
    assert history.finished[-1][0] == "error"


@pytest.mark.parametrize("kind", _ENGINES)
def test_an_admins_deferred_work_keeps_its_privilege(kind, users, script, history, ran):
    with _as(users, Role.ADMIN):
        _entry, fire = _register(kind, script)
    fire()
    assert ran == [_PROBE, _SIGN]
    assert history.finished[-1][0] == "ok"


@pytest.mark.parametrize("kind", _ENGINES)
def test_work_registered_without_rbac_runs_as_before(kind, script, history, ran):
    entry, fire = _register(kind, script)
    assert entry.owner is None
    fire()
    assert ran == [_PROBE, _SIGN]
    assert history.finished[-1][0] == "ok"


# --- the role is looked up when the work fires ------------------------------

@pytest.mark.parametrize("kind", _ENGINES)
def test_a_demoted_admins_work_loses_the_privilege(kind, users, script, history, ran):
    with _as(users, Role.ADMIN):
        _entry, fire = _register(kind, script)
    users.set_role("admin-user", Role.OPERATOR)
    fire()
    assert ran == [_PROBE]
    assert history.finished[-1][0] == "error"


@pytest.mark.parametrize("kind", _ENGINES)
def test_work_of_a_user_demoted_to_viewer_or_removed_does_not_run(
        kind, users, script, history, ran):
    with _as(users, Role.OPERATOR):
        _entry, fire = _register(kind, script)
    users.set_role("operator-user", Role.VIEWER)
    fire()
    assert ran == []
    status, error = history.finished[-1]
    assert status == "error"
    assert "drive_input" in error
    users.remove_user("operator-user")
    fire()
    assert ran == []
    assert "no longer in the user store" in history.finished[-1][1]


def test_a_change_made_by_another_process_is_seen(users, script, history, ran):
    """The store is re-read when its file changed, as it is for a request."""
    with _as(users, Role.ADMIN):
        _entry, fire = _register("scheduler", script)
    other = UserStore(users.path)
    other.set_role("admin-user", Role.OPERATOR)
    fire()
    assert ran == [_PROBE]


def test_a_promoted_user_gains_the_privilege(users, script, history, ran):
    with _as(users, Role.OPERATOR):
        _entry, fire = _register("scheduler", script)
    users.set_role("operator-user", Role.ADMIN)
    fire()
    assert ran == [_PROBE, _SIGN]


# --- the watchdog -----------------------------------------------------------

def test_a_watchdog_rule_runs_as_its_owner(users):
    dismissed = []
    watchdog = PopupWatchdog()
    with _as(users, Role.OPERATOR):
        watchdog.add_rule(WatchdogRule(
            "popup", matcher=lambda: True,
            action=lambda: dismissed.append(current_authorization().user_id)))
    watchdog.add_rule(WatchdogRule(
        "unowned", matcher=lambda: True,
        action=lambda: dismissed.append(current_authorization())))
    assert watchdog.check_once() == 2
    assert dismissed == ["operator-user", None]
    users.remove_user("operator-user")
    assert watchdog.check_once() == 1
    assert dismissed == ["operator-user", None, None]


def test_add_window_rule_records_the_caller(users):
    watchdog = PopupWatchdog()
    with _as(users, Role.OPERATOR):
        watchdog.add_window_rule("Update available")
    assert watchdog._rules[0].owner.user_id == "operator-user"


# --- the owner record -------------------------------------------------------

def test_capture_owner_is_none_outside_a_scope_and_carries_the_store_inside(users):
    assert capture_owner() is None
    with _as(users, Role.OPERATOR):
        owner = capture_owner()
    assert (owner.user_id, owner.role, owner.store) == ("operator-user", Role.OPERATOR, users)


def test_an_owner_survives_being_saved_and_is_optional_in_an_old_entry(users, monkeypatch):
    saved = json.loads(json.dumps(DeferredOwner("admin-user", Role.ADMIN, users).to_dict()))
    assert saved == {"user_id": "admin-user", "role": "admin"}
    loaded = DeferredOwner.from_dict(saved)
    assert loaded == DeferredOwner("admin-user", Role.ADMIN)
    assert loaded.store is None
    for old_entry in (None, {}, {"user_id": ""}, {"user_id": 3, "role": "admin"}, "admin"):
        assert DeferredOwner.from_dict(old_entry) is None
    # Read back from a file there is no store attached: the configured one is asked.
    monkeypatch.setenv(USERS_ENV, str(users.path))
    users.set_role("admin-user", Role.VIEWER)
    assert resolve_owner(loaded).role == Role.VIEWER
    # With RBAC switched off since, the role recorded at registration stands.
    monkeypatch.delenv(USERS_ENV)
    assert resolve_owner(loaded).role == Role.ADMIN


def test_job_records_built_the_old_way_still_construct():
    """``owner`` is keyword-only, so positional construction is unchanged."""
    job = ScheduledJob("id", "script.json", 5.0, None, True, None, 0, True, 1.0)
    assert job.owner is None
    assert job.next_run_ts == pytest.approx(1.0)
    trigger = WindowAppearsTrigger("id", "script.json", True, True, 0, 0.5, 0.0, "title")
    assert trigger.owner is None
    assert trigger.title_substring == "title"


def test_owner_scope_restores_the_thread_and_refuses_before_running(users):
    owner = DeferredOwner("viewer-user", Role.VIEWER, users)
    outer = AuthorizationContext("outer", Role.ADMIN)
    with authorization_scope(outer):
        with owner_scope(None):
            assert current_authorization() is outer
        with pytest.raises(AuthorizationError) as refused:
            with owner_scope(owner):
                pytest.fail("a viewer's deferred work must not start")
        assert refused.value.capability == "drive_input"
        assert current_authorization() is outer


def test_run_counting_failures_takes_the_owner(users):
    seen = []
    owner = DeferredOwner("operator-user", Role.OPERATOR, users)
    run_counting_failures(lambda: seen.append(current_authorization().role), owner=owner)
    run_counting_failures(lambda: seen.append(current_authorization()))
    assert seen == [Role.OPERATOR, None]
