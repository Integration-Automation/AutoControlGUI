"""The last callers that ran on the process-lifetime variable scope.

U-20261009-07 gave every top-level run its own ``VariableScope`` but left
four callers on the module executor's process scope: ``run --dry-run --var``,
observer callbacks (``AC_observe_add`` and the MCP ``ac_observe_add``), a plan
run by ``run_from_description`` and a state machine's default runner. Each
has a deliberate scope now:

* a dry run seeds ``--var`` into the run's own scope;
* an observer callback keeps a snapshot of the variables visible when it was
  registered and every firing runs in a fresh scope seeded from it;
* a plan and a state machine are a run of their own from Python and a step of
  the calling run from an action list.

Only variable commands and a probe registered for the test run here; the
observer predicates are fakes, so nothing reads the screen.
"""
import json

import pytest

from je_auto_control.utils.executor import action_executor
from je_auto_control.utils.executor.action_executor import (
    Executor, execute_action, execute_action_with_vars, executor,
)
from je_auto_control.utils.script_vars import execution_scope
from je_auto_control.utils.script_vars.execution import current_scope

PROBE = "AC_scope_probe"
_SET_USER = ["AC_set_var", {"name": "user", "value": "alice"}]
_READ_USER = [PROBE, {"value": "${user}"}]


@pytest.fixture
def seen():
    """Register a probe command on the module executor; restore it afterwards."""
    values = []
    saved = executor.variables.as_dict()
    executor.variables.clear()
    executor.event_dict[PROBE] = lambda value=None: values.append(value) or value
    yield values
    executor.event_dict.pop(PROBE, None)
    executor.variables.clear()
    executor.variables.update_many(saved)


def _failed(record):
    return [value for value in record.values() if "Unknown variable" in str(value)]


# --- run_level_scope -------------------------------------------------------

def run_level_scope():
    """Imported late so the rest of the file runs against a tree without it."""
    from je_auto_control.utils.script_vars import execution
    return execution.run_level_scope()


def test_run_level_scope_is_fresh_when_nothing_is_running(seen):
    executor.variables.set("leftover", 1)
    with run_level_scope() as scope:
        assert current_scope() is scope
        assert "leftover" not in scope
        executor.execute_action([_SET_USER])
        assert scope.get_value("user") == "alice"
    assert current_scope() is None
    assert "user" not in executor.variables


def test_run_level_scope_joins_the_enclosing_run(seen):
    with execution_scope({"user": "bob"}) as outer:
        with run_level_scope() as scope:
            assert scope is outer
            executor.execute_action([["AC_set_var", {"name": "n", "value": 1}]])
        assert current_scope() is outer
        assert outer.get_value("n") == 1


def test_run_level_scope_is_dropped_after_an_error(seen):
    with pytest.raises(RuntimeError):
        with run_level_scope():
            executor.execute_action([_SET_USER])
            raise RuntimeError("boom")
    assert current_scope() is None
    assert "user" not in executor.variables


# --- je_auto_control run --dry-run --var -----------------------------------

def test_dry_run_vars_do_not_stay_in_the_process_scope(seen, tmp_path, capsys):
    from je_auto_control.cli import main
    script = tmp_path / "script.json"
    script.write_text(json.dumps([_READ_USER]), encoding="utf-8")
    assert main(["run", str(script), "--dry-run", "--var", "user=alice"]) == 0
    assert "Unknown variable" not in capsys.readouterr().out   # the seed reached the run
    assert seen == []                                           # ...which executes nothing
    assert "user" not in executor.variables


def test_dry_run_with_vars_still_accepts_loop_bodies(seen, tmp_path, capsys):
    from je_auto_control.cli import main
    script = tmp_path / "script.json"
    script.write_text(json.dumps([["AC_for_each", {
        "items": "${names}", "as": "name", "body": [[PROBE, {"value": "${name}"}]],
    }]]), encoding="utf-8")
    assert main(["run", str(script), "--dry-run", "--var", 'names=["a","b"]']) == 0
    assert "Unknown variable" not in capsys.readouterr().out
    assert "names" not in executor.variables


# --- observer callbacks ----------------------------------------------------

class _Flag:
    """A fake predicate: the test says when the watched thing is there."""

    def __init__(self):
        self.value = False

    def __call__(self):
        return self.value


@pytest.fixture
def watch(monkeypatch):
    """A private observer and a fake predicate for both registration routes."""
    from je_auto_control.utils import observer as observer_package
    from je_auto_control.utils.mcp_server.tools import _handlers_locators
    from je_auto_control.utils.observer import ScreenObserver
    flag = _Flag()
    private = ScreenObserver()
    monkeypatch.setattr(observer_package, "default_observer", private)
    monkeypatch.setattr(action_executor, "_observe_predicate", lambda kind, params: flag)
    monkeypatch.setattr(_handlers_locators, "_observe_predicate", lambda kind, params: flag)
    return flag, private


def _appear(flag, private):
    """One vanish-then-appear transition, polled on this thread."""
    flag.value = False
    private.poll_once()
    flag.value = True
    return private.poll_once()


_COUNT_UP = [["AC_inc_var", {"name": "n"}], [PROBE, {"value": "${n}"}]]


def test_observer_callback_sees_the_variables_of_its_registration(seen, watch):
    flag, private = watch
    execute_action_with_vars([["AC_observe_add", {
        "name": "w", "kind": "image", "actions": [_READ_USER]}]], {"user": "alice"})
    assert "user" not in executor.variables      # the registering run is over
    assert _appear(flag, private)
    assert seen == ["alice"]


def test_observer_callback_writes_reach_nobody_else(seen, watch):
    flag, private = watch
    execute_action_with_vars([["AC_observe_add", {
        "name": "w", "kind": "image", "actions": _COUNT_UP}]], {"n": 10})
    _appear(flag, private)
    _appear(flag, private)
    # Every firing starts from the snapshot: 11 twice, not 11 then 12.
    assert seen == [11, 11]
    assert "n" not in executor.variables


def test_observer_callback_does_not_read_or_write_the_polling_run(seen, watch):
    flag, private = watch
    execute_action_with_vars([["AC_observe_add", {
        "name": "w", "kind": "image", "actions": [_READ_USER, _SET_USER]}]], {})
    flag.value = True
    record = execute_action_with_vars(
        [["AC_observe_poll", {}], [PROBE, {"value": "${user}"}]], {"user": "poller"})
    # The callback's ${user} is unknown (it was registered without one) and
    # its AC_set_var did not overwrite the polling run's value.
    assert seen == ["poller"]
    assert not _failed(record)


def test_observer_callback_registered_outside_a_run_snapshots_the_process_scope(seen, watch):
    flag, private = watch
    executor.variables.set("user", "process")
    execute_action([["AC_observe_add", {
        "name": "w", "kind": "image", "actions": [_READ_USER, _SET_USER]}]])
    executor.variables.set("user", "changed-later")
    _appear(flag, private)
    assert seen == ["process"]
    assert executor.variables.get_value("user") == "changed-later"


def test_observer_callback_fired_on_the_observer_thread_is_isolated(seen, watch):
    import threading
    flag, private = watch
    execute_action_with_vars([["AC_observe_add", {
        "name": "w", "kind": "image", "actions": _COUNT_UP}]], {"n": 1})
    flag.value = True
    worker = threading.Thread(target=private.poll_once, daemon=True)
    worker.start()
    worker.join(5)
    assert not worker.is_alive()
    assert seen == [2]
    assert "n" not in executor.variables


def test_mcp_observe_callback_runs_in_its_own_scope(seen, watch):
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    flag, private = watch
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    executor.variables.set("user", "process")
    tools["ac_observe_add"].invoke({
        "name": "w", "kind": "image", "actions": [_SET_USER, _READ_USER, _COUNT_UP[0]]})
    _appear(flag, private)
    _appear(flag, private)
    # Registered inside a tool call, whose scope is empty: the callback does
    # not see the process scope, and what it sets is gone between firings.
    assert seen == ["alice", "alice"]
    assert executor.variables.as_dict() == {"user": "process"}


# --- run_from_description --------------------------------------------------

class _Backend:
    """An LLM backend that answers with a fixed plan."""

    name = "fake"
    available = True

    def __init__(self, plan):
        self._plan = plan

    def complete(self, prompt, system=None, model=None, max_tokens=2048):
        return json.dumps(self._plan)


def _plan(plan, on=executor):
    from je_auto_control.utils.llm.planner import run_from_description
    return run_from_description("do it", on, backend=_Backend(plan))


def test_a_plan_run_from_python_gets_its_own_scope(seen):
    executor.variables.set("user", "leftover")
    outcome = _plan([_READ_USER])
    assert seen == []
    assert _failed(outcome["record"])
    _plan([_SET_USER, _READ_USER])
    assert seen == ["alice"]
    assert executor.variables.get_value("user") == "leftover"


def test_a_plan_inside_a_run_is_a_step_of_that_run(seen):
    with execution_scope({"user": "bob"}) as scope:
        _plan([_READ_USER, ["AC_set_var", {"name": "made", "value": 1}]])
        assert scope.get_value("made") == 1
    assert seen == ["bob"]


def test_a_plan_on_a_private_executor_uses_that_executors_scope(seen):
    private = Executor()
    private.event_dict[PROBE] = executor.event_dict[PROBE]
    private.variables.set("user", "private")
    _plan([_READ_USER], on=private)
    assert seen == ["private"]


# --- the state machine's default runner ------------------------------------

def _machine(*on_enter):
    return {"initial": "a", "states": {
        "a": {"on_enter": list(on_enter[:1]), "transitions": [{"go_to": "b"}]},
        "b": {"on_enter": list(on_enter[1:]), "final": True},
    }}


def test_a_state_machine_run_from_python_gets_its_own_scope(seen):
    from je_auto_control.utils.state_machine import run_state_machine
    executor.variables.set("user", "leftover")
    run_state_machine(_machine(_READ_USER))
    assert seen == []                               # the process scope is not read
    # ...but states of one run share what they set
    run_state_machine(_machine(_SET_USER, _READ_USER))
    assert seen == ["alice"]
    assert executor.variables.get_value("user") == "leftover"


def test_a_state_machine_inside_a_run_uses_that_runs_scope(seen):
    record = execute_action_with_vars([
        ["AC_run_state_machine", {"spec": _machine(
            _READ_USER, ["AC_set_var", {"name": "user", "value": "machine"}])}],
        _READ_USER,
    ], {"user": "run"})
    assert not _failed(record)
    assert seen == ["run", "machine"]
    assert "user" not in executor.variables


def test_a_state_machine_in_a_parallel_branch_uses_the_branch_scope(seen):
    branches = [[["AC_set_var", {"name": "user", "value": name}],
                 ["AC_run_state_machine", {"spec": _machine(_READ_USER)}]]
                for name in ("left", "right")]
    execute_action_with_vars([["AC_parallel", {"branches": branches}]], {"user": "parent"})
    assert sorted(seen) == ["left", "right"]


def test_default_runner_takes_one_action_or_a_list_of_actions(seen):
    from je_auto_control.utils.state_machine import run_state_machine
    run_state_machine({"initial": "a", "states": {"a": {"final": True, "on_enter": [
        [PROBE, {"value": "single"}],
        [[PROBE, {"value": "first"}], [PROBE, {"value": "second"}]],
        [PROBE],
    ]}}})
    assert seen == ["single", "first", "second", None]


def test_a_custom_state_machine_runner_shares_the_machines_run_scope(seen):
    from je_auto_control.utils.state_machine import StateMachine
    machine = StateMachine(
        _machine(_SET_USER, _READ_USER),
        execute_action=lambda action: execute_action([action]))
    machine.run()
    assert seen == ["alice"]
    assert "user" not in executor.variables
