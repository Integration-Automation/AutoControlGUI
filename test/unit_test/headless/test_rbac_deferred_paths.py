"""Observer callbacks, planner runs and state machines keep their caller's identity.

Scheduler jobs, triggers, hotkeys, webhooks, e-mail triggers and watchdog
rules already run as whoever registered them. Three paths did not:

* an observer callback (``AC_observe_add`` / ``ac_observe_add`` /
  ``ScreenObserver.add``) fires on the observer's thread, or inside whoever
  polls, long after the request that registered it -- with no identity, so an
  operator's watch could run a privileged command unchecked;
* a state machine built in a request and run on another thread, and a plan
  executed on another thread, ran with no identity for the same reason.

Nothing here touches the real mouse, keyboard or screen: predicates are
synthetic, the LLM backend is a fake, and the privileged command is replaced
by a recorder.
"""
import json
import threading

import pytest

from je_auto_control.utils.executor.action_executor import execute_action, executor
from je_auto_control.utils.llm.planner import run_from_description
from je_auto_control.utils.mcp_server.tools import _handlers_locators
from je_auto_control.utils.observer import observer as observer_module
from je_auto_control.utils.observer.observer import ScreenObserver
from je_auto_control.utils.rbac import (
    USERS_ENV, DeferredOwner, Role, UserStore, authorization_scope, capture_owner,
    current_authorization, resolve_token,
)
from je_auto_control.utils.rbac.deferred import adopted_scope, owner_scope
from je_auto_control.utils.state_machine import StateMachine

_SIGN = "AC_sign_action_file"
_PROBE = "AC_deferred_probe"
_ACTIONS = [[_PROBE], [_SIGN, {"path": "x"}]]
_WAIT = 10.0


@pytest.fixture(autouse=True)
def _no_ambient_rbac(monkeypatch):
    monkeypatch.delenv(USERS_ENV, raising=False)


@pytest.fixture()
def ran(monkeypatch):
    """Which commands actually ran, and as whom."""
    calls = []

    def record(name):
        def run(**_kwargs):
            caller = current_authorization()
            calls.append((name, None if caller is None else caller.user_id))
        return run
    monkeypatch.setitem(executor.event_dict, _SIGN, record(_SIGN))
    monkeypatch.setitem(executor.event_dict, _PROBE, record(_PROBE))
    return calls


@pytest.fixture()
def users(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.tokens = {role: store.add_user(user_id=f"{role}-user", display_name=role, role=role)
                    for role in Role.all()}
    return store


@pytest.fixture()
def observer(monkeypatch):
    """A fresh observer standing in for the process-wide one; never started."""
    fresh = ScreenObserver()
    monkeypatch.setattr(observer_module, "default_observer", fresh)
    monkeypatch.setattr("je_auto_control.utils.observer.default_observer", fresh)
    return fresh


def _as(users, role):
    return authorization_scope(resolve_token(users, users.tokens[role]))


def _on_thread(work):
    """Run ``work`` on a fresh thread -- one with no authorisation scope of its own."""
    outcome = []

    def run():
        try:
            outcome.append(("ok", work()))
        except Exception as error:  # noqa: BLE001  # reason: handed back to the test thread
            outcome.append(("error", error))
    thread = threading.Thread(target=run)
    thread.start()
    thread.join(_WAIT)
    assert outcome, "the worker did not finish"
    return outcome[0]


def _present():
    return (1, 1)


_REGISTRARS = {
    "executor": lambda: execute_action(
        [["AC_observe_add", {"name": "watch", "kind": "pixel", "actions": _ACTIONS}]]),
    "mcp": lambda: _handlers_locators.observe_add("watch", kind="pixel", actions=_ACTIONS),
}


def _register_watch(how, observer, monkeypatch):
    """Register a watch through ``how`` whose predicate is always present."""
    monkeypatch.setattr(observer_module, "pixel_predicate", lambda _x, _y: _present)
    monkeypatch.setattr("je_auto_control.utils.observer.pixel_predicate",
                        lambda _x, _y: _present)
    _REGISTRARS[how]()
    return observer._rules[-1]


# --- observer callbacks ------------------------------------------------------------------

@pytest.mark.parametrize("how", sorted(_REGISTRARS))
def test_an_operators_watch_cannot_run_a_privileged_command(how, users, observer, ran,
                                                            monkeypatch):
    with _as(users, Role.OPERATOR):
        rule = _register_watch(how, observer, monkeypatch)
    assert rule.owner == DeferredOwner("operator-user", Role.OPERATOR)
    status, fired = _on_thread(observer.poll_once)
    assert status == "ok" and len(fired) == 1
    assert ran == [(_PROBE, "operator-user")]


@pytest.mark.parametrize("how", sorted(_REGISTRARS))
def test_an_admins_watch_keeps_its_privilege(how, users, observer, ran, monkeypatch):
    with _as(users, Role.ADMIN):
        _register_watch(how, observer, monkeypatch)
    _on_thread(observer.poll_once)
    assert ran == [(_PROBE, "admin-user"), (_SIGN, "admin-user")]


@pytest.mark.parametrize("how", sorted(_REGISTRARS))
def test_a_watch_registered_without_rbac_runs_as_before(how, observer, ran, monkeypatch):
    rule = _register_watch(how, observer, monkeypatch)
    assert rule.owner is None
    _on_thread(observer.poll_once)
    assert ran == [(_PROBE, None), (_SIGN, None)]


def test_a_watch_fires_as_its_owner_even_when_someone_else_polls(users, observer, ran,
                                                                 monkeypatch):
    with _as(users, Role.OPERATOR):
        _register_watch("executor", observer, monkeypatch)
    with _as(users, Role.ADMIN):
        observer.poll_once()
        assert current_authorization().user_id == "admin-user"
    assert ran == [(_PROBE, "operator-user")], "the poller's role is not lent to the watch"


def test_a_removed_or_demoted_owners_watch_does_not_fire_its_callback(users, observer, ran,
                                                                      monkeypatch):
    with _as(users, Role.OPERATOR):
        rule = _register_watch("executor", observer, monkeypatch)
    users.set_role("operator-user", Role.VIEWER)
    observer.poll_once()
    assert ran == []
    rule.last = observer_module._UNSET       # make the next poll a transition again
    users.remove_user("operator-user")
    observer.poll_once()
    assert ran == []


def test_python_callers_get_the_owner_too(users):
    seen = []
    watcher = ScreenObserver()
    with _as(users, Role.OPERATOR):
        watcher.add("direct", _present, lambda _event, _value: seen.append(current_authorization()))
    _on_thread(watcher.poll_once)
    assert [caller.user_id for caller in seen] == ["operator-user"]


# --- state machine -------------------------------------------------------------------------

def _machine():
    return StateMachine({"initial": "only", "states": {
        "only": {"final": True, "on_enter": [[_PROBE], [_SIGN, {"path": "x"}]]}}})


def test_a_state_machine_run_on_another_thread_is_still_its_builders(users, ran):
    with _as(users, Role.OPERATOR):
        machine = _machine()
    status, _result = _on_thread(machine.run)
    assert status == "ok"
    assert ran == [(_PROBE, "operator-user")]


def test_an_admins_state_machine_keeps_its_privilege_on_another_thread(users, ran):
    with _as(users, Role.ADMIN):
        machine = _machine()
    _on_thread(machine.run)
    assert ran == [(_PROBE, "admin-user"), (_SIGN, "admin-user")]


def test_a_state_machine_built_without_rbac_runs_as_before(ran):
    _on_thread(_machine().run)
    assert ran == [(_PROBE, None), (_SIGN, None)]


def test_a_state_machine_run_inside_a_request_uses_that_request(users, ran):
    """The caller being served decides; a stored owner only fills an empty thread."""
    with _as(users, Role.ADMIN):
        machine = _machine()
    with _as(users, Role.OPERATOR):
        machine.run()
    assert ran == [(_PROBE, "operator-user")]


def test_a_removed_users_state_machine_does_not_run(users, ran):
    with _as(users, Role.OPERATOR):
        machine = _machine()
    users.remove_user("operator-user")
    status, error = _on_thread(machine.run)
    assert status == "error" and "no longer in the user store" in str(error)
    assert ran == []


# --- planner ----------------------------------------------------------------------------------

class _FakeBackend:
    available = True

    def complete(self, _prompt, **_kwargs):
        return json.dumps(_ACTIONS)


def _plan(owner=None):
    return run_from_description("sign it", executor, backend=_FakeBackend(), owner=owner)


def test_a_plan_handed_to_another_thread_runs_as_the_given_owner(users, ran):
    with _as(users, Role.OPERATOR):
        owner = capture_owner()
    status, _result = _on_thread(lambda: _plan(owner))
    assert status == "ok"
    assert ran == [(_PROBE, "operator-user")]


def test_an_admins_plan_keeps_its_privilege_on_another_thread(users, ran):
    with _as(users, Role.ADMIN):
        owner = capture_owner()
    _on_thread(lambda: _plan(owner))
    assert ran == [(_PROBE, "admin-user"), (_SIGN, "admin-user")]


def test_a_plan_inside_a_request_is_that_requests(users, ran):
    with _as(users, Role.OPERATOR):
        _plan()
    assert ran == [(_PROBE, "operator-user")]


def test_a_plan_without_rbac_runs_as_before(ran):
    _plan()
    assert ran == [(_PROBE, None), (_SIGN, None)]


# ``AC_llm_run`` takes no ``owner``: an action is executed on the thread that
# runs its list, so the caller is already there -- the request's own scope, or
# the ``owner_scope`` a scheduler / trigger / hotkey opened for the entry's
# owner. An ``owner`` argument in an action list would only let its author
# name somebody else.

_LLM_RUN = [["AC_llm_run", {"description": "sign it"}]]


@pytest.fixture()
def fake_llm(monkeypatch):
    monkeypatch.setattr("je_auto_control.utils.llm.planner.get_backend", _FakeBackend)


def test_ac_llm_run_inside_a_request_runs_as_that_request(users, ran, fake_llm):
    with _as(users, Role.OPERATOR):
        execute_action(_LLM_RUN, raise_on_error=False)
    assert ran == [(_PROBE, "operator-user")]
    ran.clear()
    with _as(users, Role.ADMIN):
        execute_action(_LLM_RUN)
    assert ran == [(_PROBE, "admin-user"), (_SIGN, "admin-user")]


def test_ac_llm_run_in_deferred_work_runs_as_the_works_owner(users, ran, fake_llm):
    with _as(users, Role.OPERATOR):
        owner = capture_owner()

    def fire():
        with owner_scope(owner):  # what the scheduler does around a job
            return execute_action(_LLM_RUN, raise_on_error=False)

    status, _result = _on_thread(fire)
    assert status == "ok"
    assert ran == [(_PROBE, "operator-user")]


def test_ac_llm_run_rejects_an_owner_argument(ran, fake_llm):
    record = execute_action(
        [["AC_llm_run", {"description": "sign it",
                         "owner": {"user_id": "admin-user", "role": "admin"}}]],
        raise_on_error=False)
    assert ran == []
    assert "owner" in str(list(record.values())[0])


# --- the helper --------------------------------------------------------------------------------

def test_adopted_scope_yields_to_a_caller_already_in_scope(users):
    with _as(users, Role.ADMIN):
        owner = capture_owner()
    with _as(users, Role.VIEWER), adopted_scope(owner):
        assert current_authorization().user_id == "viewer-user"
    with adopted_scope(owner):
        assert current_authorization().user_id == "admin-user"
    with adopted_scope(None):
        assert current_authorization() is None
