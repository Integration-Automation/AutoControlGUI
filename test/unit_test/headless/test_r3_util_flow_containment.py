"""Round-3 audit regressions: execution-flow containment fixes.

Covers findings 1 (DAG runner), 2 (callback executor), 5 (test-suite runner),
and 6 (self-healing replay). Each asserts that a framework exception raised by
an injected callable is *contained* into a result rather than crashing the
surrounding driver. Fully headless — no real input, no Qt.
"""
import types

import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, AutoControlMouseException,
)


# --- Finding 1: DAG runner ------------------------------------------------

def test_run_dag_contains_framework_exception():
    from je_auto_control.utils.dag.runner import (
        STATUS_FAILED, STATUS_SKIPPED, run_dag,
    )
    definition = {"nodes": [
        {"id": "a", "actions": [["AC_noop", {}]]},
        {"id": "b", "actions": [["AC_noop", {}]], "depends_on": ["a"]},
    ]}

    def boom_runner(node, _definition):
        raise AutoControlActionException(f"bad command in {node.id}")

    result = run_dag(definition, local_runner=boom_runner)
    assert result.succeeded is False
    assert result.nodes["a"].status == STATUS_FAILED
    assert "AutoControlActionException" in (result.nodes["a"].error or "")
    # Downstream node is skipped (cascade), never left "running".
    assert result.nodes["b"].status == STATUS_SKIPPED


# --- Finding 2: callback executor ----------------------------------------

def test_callback_failure_preserves_trigger_result():
    from je_auto_control.utils.callback.callback_function_executor import (
        CallbackFunctionExecutor,
    )
    executor = CallbackFunctionExecutor()
    executor.event_dict["_r3_trigger_ok"] = lambda **_kw: "TRIGGER_OK"

    def bad_callback():
        raise ValueError("callback boom")

    result = executor.callback_function("_r3_trigger_ok", bad_callback)
    # A callback failure must NOT discard the already-computed trigger result.
    assert result == "TRIGGER_OK"


def test_callback_trigger_framework_exception_returns_none():
    from je_auto_control.utils.callback.callback_function_executor import (
        CallbackFunctionExecutor,
    )
    executor = CallbackFunctionExecutor()

    def boom(**_kw):
        raise AutoControlMouseException("mouse fail")

    executor.event_dict["_r3_trigger_bad"] = boom
    ran = []
    result = executor.callback_function(
        "_r3_trigger_bad", lambda: ran.append(1))
    # Framework trigger failure is handled (not propagated) and returns None;
    # the callback does not run when the trigger failed.
    assert result is None
    assert ran == []


# --- Finding 5: test-suite runner ----------------------------------------

class _FakeExecutor:
    """Minimal executor stand-in for run_suite."""

    def __init__(self, on_execute=None):
        self.variables = types.SimpleNamespace(set=lambda *_a, **_k: None)
        self.executed = []
        self._on_execute = on_execute

    def execute_action(self, actions, raise_on_error=False):
        self.executed.append(actions)
        if self._on_execute is not None:
            return self._on_execute(actions, raise_on_error)
        return {}


def test_run_actions_scores_lookup_error_as_error():
    from je_auto_control.utils.test_suite.runner import run_suite
    from je_auto_control.utils.test_suite.result import STATUS_ERROR

    def raise_key_error(_actions, _raise):
        raise KeyError("missing arg")  # LookupError, outside the old tuple

    spec = {"name": "s", "cases": [{"name": "c1", "actions": [["x"]]}]}
    result = run_suite(spec, executor=_FakeExecutor(raise_key_error))
    assert len(result.cases) == 1
    assert result.cases[0].status == STATUS_ERROR


def test_bad_case_does_not_abort_suite_and_teardown_runs():
    from je_auto_control.utils.test_suite.runner import run_suite
    from je_auto_control.utils.test_suite.result import (
        STATUS_ERROR, STATUS_PASSED,
    )
    spec = {
        "name": "s",
        "cases": [
            {"name": "bad",
             "data": {"kind": "csv", "path": "/no/such/dir/missing.csv"},
             "actions": [["x"]]},
            {"name": "good", "actions": []},
        ],
        "teardown": [["td"]],
    }
    executor = _FakeExecutor()
    result = run_suite(spec, executor=executor)
    by_name = {case.name: case.status for case in result.cases}
    # The malformed (unexpandable) case scores error but does not kill the run.
    assert by_name["bad"] == STATUS_ERROR
    assert by_name["good"] == STATUS_PASSED
    # Teardown always runs, even though a case blew up during expansion.
    assert [["td"]] in executor.executed


# --- Finding 6: self-healing replay --------------------------------------

def test_self_healing_replay_contains_framework_exception():
    from je_auto_control.utils.semantic_recording.self_healing import (
        SelfHealingReplayer,
    )

    def execute(_action):
        raise AutoControlActionException("boom")

    replayer = SelfHealingReplayer(execute, max_retries=1)
    result = replayer.replay([{"action": "mouse_click", "x": 1, "y": 2}])
    assert result.succeeded is False
    assert result.steps[0].success is False
    assert "AutoControlActionException" in (result.steps[0].last_error or "")


def test_enrich_recording_passes_through_non_mapping():
    from je_auto_control.utils.semantic_recording.enrich import enrich_recording
    actions = [{"action": "key_press", "key": "a"}, "not-a-mapping", 42]
    out = enrich_recording(actions)
    assert out[1] == "not-a-mapping"
    assert out[2] == 42


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
