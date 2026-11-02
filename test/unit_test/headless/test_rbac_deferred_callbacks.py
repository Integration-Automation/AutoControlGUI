"""Webhook, IMAP and observer callbacks preserve their registration authority."""
import json
import threading
import urllib.error
import urllib.request
from email.message import EmailMessage

import pytest

from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, AuthorizationError, authorization_scope, current_authorization, resolve_token,
)
from je_auto_control.utils.rbac.users import Role, UserStore
from je_auto_control.utils.run_history.history_store import HistoryStore

KINDS = ("webhook", "email", "observer")
ADMIN = AuthorizationContext("ambient-admin", Role.ADMIN)
OPERATOR = AuthorizationContext("owner", Role.OPERATOR)


@pytest.fixture
def callback_work(tmp_path, monkeypatch):
    from je_auto_control.utils.triggers import email_trigger, webhook_server

    history = HistoryStore()
    for module in (email_trigger, webhook_server):
        monkeypatch.setattr(module, "default_history_store", history)
        monkeypatch.setattr(module, "capture_error_snapshot", lambda *_args: None)
    path = tmp_path / "actions.json"
    calls = []
    monkeypatch.setitem(executor.event_dict, "AC_sign_action_file", lambda: calls.append(current_authorization()))
    path.write_text(json.dumps([["AC_sign_action_file"]]), encoding="utf-8")

    def create(kind, context):
        registered = []
        with authorization_scope(context):
            if kind == "webhook":
                service = webhook_server.WebhookTriggerServer()
                registered.append(service.add("/hook", str(path)))
                def fire():
                    return service.fire(registered[0], {})
            elif kind == "email":
                service = email_trigger.EmailTriggerWatcher()
                registered.append(service.add("imap.invalid", "test", "test-password", str(path), mark_seen=False))
                message = EmailMessage()
                message["Subject"] = "Test"
                message.set_content("Body")
                monkeypatch.setattr(email_trigger, "_fetch_message", lambda *_args: message)
                def fire():
                    return service._fire_for_uid(object(), registered[0], "1")
            else:
                from je_auto_control.utils.json.json_file import read_executable_action_json
                from je_auto_control.utils.observer.observer import ScreenObserver
                service = ScreenObserver()
                service.add("watch", lambda: True,
                            lambda *_args: executor.execute_action(read_executable_action_json(str(path))))
                fire = service.poll_once
        return service, fire

    yield create, calls, path
    history.close()


@pytest.mark.parametrize("kind", KINDS)
def test_callbacks_do_not_borrow_the_dispatching_administrators_role(kind, callback_work):
    create, calls, _ = callback_work
    _, fire = create(kind, OPERATOR)
    with authorization_scope(ADMIN):
        fire()
        assert current_authorization() is ADMIN
    assert calls == []


@pytest.mark.parametrize("kind", KINDS)
def test_callbacks_keep_the_registering_administrator_identity(kind, callback_work):
    create, calls, _ = callback_work
    _, fire = create(kind, ADMIN)
    with authorization_scope(OPERATOR):
        fire()
    assert calls == [ADMIN]


@pytest.mark.parametrize("kind", KINDS)
def test_callback_runs_have_fresh_variables_and_clear_unscoped_authority(kind, callback_work, monkeypatch):
    from je_auto_control.utils.script_vars.execution import current_scope, execution_scope
    create, _, path = callback_work
    seen = []
    path.write_text(json.dumps([["AC_slugify", {"text": "x"}]]), encoding="utf-8")
    monkeypatch.setitem(executor.event_dict, "AC_slugify", lambda text: seen.append(
        (current_authorization(), current_scope())))
    _, fire = create(kind, None)
    with authorization_scope(ADMIN), execution_scope() as outer:
        fire()
    assert len(seen) == 1
    assert seen[0][0] is None
    assert seen[0][1] is not None and seen[0][1] is not outer


@pytest.mark.parametrize("kind", KINDS)
def test_deleted_callback_owner_cannot_execute(kind, callback_work, tmp_path):
    create, calls, _ = callback_work
    store = UserStore(tmp_path / "users.json")
    token = store.add_user(user_id="owner", display_name="Owner", role=Role.ADMIN)
    _, fire = create(kind, resolve_token(store, token))
    UserStore(store.path).remove_user("owner")
    with authorization_scope(ADMIN):
        if kind == "webhook":
            with pytest.raises(AuthorizationError):
                fire()
        else:
            fire()
    assert calls == []


@pytest.mark.parametrize("kind", KINDS)
def test_live_callback_dispatch_binds_owner_and_isolates_variables(kind, callback_work, monkeypatch):
    from je_auto_control.utils.script_vars.execution import current_scope
    create, _, path = callback_work
    path.write_text(json.dumps([["AC_slugify", {"text": "x"}]]), encoding="utf-8")
    reached = threading.Event()
    finished = threading.Event()
    seen = []

    def step(text):
        seen.append((current_authorization(), current_scope()))
        reached.set()

    monkeypatch.setitem(executor.event_dict, "AC_slugify", step)
    service, _ = create(kind, OPERATOR)
    if kind == "email":
        from je_auto_control.utils.triggers import email_trigger

        class FakeIMAP:
            def select(self, *_args, **_kwargs):
                return "OK", []

            def response(self, *_args):
                return "OK", [b"1"]

            def uid(self, *_args):
                return "OK", [b"1"]

            def logout(self):
                finished.set()

        def connect(_trigger):
            assert current_authorization() == OPERATOR
            return FakeIMAP()

        monkeypatch.setattr(email_trigger, "_connect", connect)
    try:
        with authorization_scope(ADMIN):
            if kind == "webhook":
                host, port = service.start("127.0.0.1", 0)
                request = urllib.request.Request(f"http://{host}:{port}/hook", data=b"", method="POST")
                with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310  # reason: local ephemeral test server
                    assert response.status == 200
            else:
                service.start()
        assert reached.wait(5), f"{kind} did not dispatch"
        if kind == "email":
            assert finished.wait(5), "mail polling did not release its client"
    finally:
        service.stop()
    assert len(seen) == 1
    assert seen[0][0] == OPERATOR
    assert seen[0][1] is not None
    assert current_authorization() is None


def test_deleted_email_owner_cannot_open_the_mailbox(callback_work, monkeypatch, tmp_path):
    from je_auto_control.utils.triggers import email_trigger
    create, _, _ = callback_work
    store = UserStore(tmp_path / "users.json")
    token = store.add_user(user_id="owner", display_name="Owner", role=Role.ADMIN)
    service, _ = create("email", resolve_token(store, token))
    UserStore(store.path).remove_user("owner")
    connected = []
    monkeypatch.setattr(email_trigger, "_connect", lambda *_args: connected.append(True))
    assert service.poll_once() == 0
    assert connected == []


def test_http_webhook_refuses_a_deleted_owner_instead_of_acknowledging_a_fire(callback_work, tmp_path):
    from je_auto_control.utils.triggers import webhook_server
    create, calls, _ = callback_work
    store = UserStore(tmp_path / "users.json")
    token = store.add_user(user_id="owner", display_name="Owner", role=Role.ADMIN)
    service, _ = create("webhook", resolve_token(store, token))
    UserStore(store.path).remove_user("owner")
    host, port = service.start("127.0.0.1", 0)
    try:
        request = urllib.request.Request(f"http://{host}:{port}/hook", data=b"", method="POST")
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)  # nosec B310  # reason: local ephemeral test server
        with caught.value as response:
            assert response.code == 403
            assert json.loads(response.read())["fired"] is False
        assert calls == []
        assert service.list_webhooks()[0].last_status == 403
        assert webhook_server.default_history_store.list_runs()[0].status == "error"
    finally:
        service.stop()


@pytest.mark.parametrize("kind", ("observer", "watchdog"))
def test_polling_a_successful_callback_does_not_erase_the_callers_failure_count(kind, monkeypatch):
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    from je_auto_control.utils.executor.action_executor import recorded_failures, reset_recorded_failures

    def fail(text):
        raise AutoControlActionException("expected failure")

    monkeypatch.setitem(executor.event_dict, "AC_slugify", fail)
    reset_recorded_failures()
    try:
        executor.execute_action([["AC_slugify", {"text": "seed"}]])
        assert recorded_failures() == 1
        monkeypatch.setitem(executor.event_dict, "AC_slugify", lambda text: text)
        actions = [["AC_slugify", {"text": "callback"}]]
        if kind == "observer":
            from je_auto_control.utils.observer.observer import ScreenObserver
            service = ScreenObserver()
            service.add("ok", lambda: True, lambda *_args: executor.execute_action(actions))
            service.poll_once()
        else:
            from je_auto_control.utils.watchdog.popup_watchdog import PopupWatchdog, WatchdogRule
            service = PopupWatchdog()
            service.add_rule(WatchdogRule("ok", lambda: True, lambda: executor.execute_action(actions)))
            assert service.check_once() == 1
        assert recorded_failures() == 1
    finally:
        reset_recorded_failures()


def test_nested_run_counts_only_new_failures_and_preserves_the_parent_count(monkeypatch):
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    from je_auto_control.utils.executor.action_executor import recorded_failures, reset_recorded_failures
    from je_auto_control.utils.run_history.run_outcome import run_counting_failures

    def fail(text):
        raise AutoControlActionException("expected failure")

    monkeypatch.setitem(executor.event_dict, "AC_slugify", fail)
    reset_recorded_failures()
    try:
        actions = [["AC_slugify", {"text": "failure"}]]
        executor.execute_action(actions)
        with pytest.raises(AutoControlActionException, match="1 action"):
            run_counting_failures(lambda: executor.execute_action(actions))
        assert recorded_failures() == 2
    finally:
        reset_recorded_failures()
