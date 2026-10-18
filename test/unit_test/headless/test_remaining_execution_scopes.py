"""CLI, planner and FSM boundaries isolate runs while nested helpers share them."""
import json
import threading
from types import SimpleNamespace

import pytest

from je_auto_control.cli import main
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.llm.planner import run_from_description
from je_auto_control.utils.script_vars.execution import current_scope, execution_scope
from je_auto_control.utils.state_machine import StateMachine, StateMachineError

PROBE = "AC_remaining_scope_probe"
SET = ["AC_set_var", {"name": "owner", "value": "child"}]
READ = [PROBE, {"value": "${owner}"}]


@pytest.fixture
def seen(monkeypatch):
    values = []
    saved = executor.variables.as_dict()
    executor.variables.clear()
    monkeypatch.setitem(executor.event_dict, PROBE, lambda value: values.append(value))
    yield values
    executor.variables.clear()
    executor.variables.update_many(saved)


def _plan(actions):
    backend = SimpleNamespace(available=True, complete=lambda *_args, **_kwargs: json.dumps(actions))
    return run_from_description("run variable actions", executor, backend=backend)


def _machine(actions, *, finish=True):
    return StateMachine({
        "initial": "first",
        "states": {
            "first": {"on_enter": actions[:1], "transitions": [{"go_to": "last"}]},
            "last": {"on_enter": actions[1:], "final": finish},
        },
    })


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("seed", [False, True])
def test_cli_run_always_uses_a_fresh_scope(seen, tmp_path, monkeypatch, capsys, dry_run, seed):
    executor.variables.set("existing", "process")
    snapshots = []
    original = executor.execute_action

    def execute(actions, **kwargs):
        snapshots.append(executor.variables.as_dict())
        return original(actions, **kwargs)

    monkeypatch.setattr(executor, "execute_action", execute)
    path = tmp_path / "run.json"
    path.write_text(json.dumps([SET, READ]), encoding="utf-8")
    args = ["run", str(path)] + (["--dry-run"] if dry_run else [])
    if seed:
        args += ["--var", "owner=seed"]
    assert main(args) == 0
    capsys.readouterr()
    assert snapshots == ([{"owner": "seed"}] if seed else [{}])
    assert executor.variables.as_dict() == {"existing": "process"}
    assert seen == ([] if dry_run else ["child"])
    assert current_scope() is None


@pytest.mark.parametrize("run", [_plan, lambda actions: _machine(actions).run()])
def test_top_level_helpers_isolate_runs_but_share_actions_within_one_run(seen, run):
    executor.variables.set("owner", "process")
    run([SET, READ])
    run([READ])
    assert seen == ["child"]
    assert executor.variables.as_dict() == {"owner": "process"}
    assert current_scope() is None


@pytest.mark.parametrize("run", [_plan, lambda actions: _machine(actions).run()])
def test_nested_helpers_reuse_the_enclosing_scope(seen, run):
    with execution_scope({"owner": "parent"}) as scope:
        run([READ, SET, READ])
        assert current_scope() is scope
        assert scope.get("owner") == "child"
    assert seen == ["parent", "child"]
    assert executor.variables.as_dict() == {}


def test_reusing_a_state_machine_starts_a_new_scope_each_time(seen):
    machine = _machine([READ])
    with execution_scope({"owner": "parent"}):
        machine.run()
    machine.run()
    assert seen == ["parent"]


def test_fsm_error_restores_the_previous_scope(seen):
    executor.variables.set("owner", "process")
    with pytest.raises(StateMachineError, match="no transition"):
        _machine([SET, READ], finish=False).run()
    assert seen == ["child"]
    assert executor.variables.as_dict() == {"owner": "process"}
    assert current_scope() is None


def test_planner_executor_error_restores_the_previous_scope(seen, monkeypatch):
    executor.variables.set("owner", "process")

    def fail(_actions):
        executor.variables.set("owner", "child")
        raise StateMachineError("execution failed")

    monkeypatch.setattr(executor, "execute_action", fail)
    with pytest.raises(StateMachineError, match="execution failed"):
        _plan([SET])
    assert executor.variables.as_dict() == {"owner": "process"}
    assert current_scope() is None


def test_cli_error_discards_dry_run_seeds(seen, tmp_path, capsys):
    path = tmp_path / "unknown.json"
    path.write_text('[["AC_no_such_command"]]', encoding="utf-8")
    assert main(["run", str(path), "--dry-run", "--var", "owner=seed"]) == 1
    capsys.readouterr()
    assert executor.variables.as_dict() == {}
    assert current_scope() is None


@pytest.mark.parametrize("run", [_plan, lambda actions: _machine(actions).run()])
def test_concurrent_helper_runs_do_not_share_variables(seen, monkeypatch, run):
    barrier = threading.Barrier(2, timeout=5)
    monkeypatch.setitem(executor.event_dict, "AC_remaining_scope_meet", lambda: barrier.wait())
    errors = []

    def worker(owner):
        try:
            run([["AC_set_var", {"name": "owner", "value": owner}],
                 ["AC_remaining_scope_meet"], READ])
        except Exception as error:  # reason: report worker failures to the asserting test thread
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(owner,)) for owner in ("left", "right")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(seen) == ["left", "right"]
    assert executor.variables.as_dict() == {}


def test_fsm_default_runner_retains_nested_action_batches(seen):
    _machine([[SET, READ]]).run()
    assert seen == ["child"]
    assert executor.variables.as_dict() == {}
