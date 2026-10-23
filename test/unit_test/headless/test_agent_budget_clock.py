"""Wall-clock changes and runtime restarts never replenish an existing task's budget."""
from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.agent_runtime.budget_clock import BudgetClock


def test_budget_survives_rollback_and_new_clock_owner(tmp_path):
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={"fixture": object()})
    try:
        task = runtime.submit({"goal": "budget", "target": "fixture", "allowed_tools": ["AC_fixture"],
            "success_criteria": [{"kind": "result_equals", "key": "ok", "value": True}]})
        runtime.store.start(task.task_id)
        row = runtime.store.get(task.task_id)
        mono, wall = [100.0], [row["started"]]
        clock = BudgetClock(runtime.store, monotonic=lambda: mono[0], wall=lambda: wall[0])
        assert clock.remaining(row) == 300
        mono[0] += 30
        wall[0] -= 3600
        assert clock.remaining(row) == 270
        replacement = BudgetClock(runtime.store, monotonic=lambda: mono[0], wall=lambda: wall[0])
        mono[0] += 20
        assert replacement.remaining(row) == 250
        mono[0] = 1
        assert replacement.remaining(row) == 0
        mono[0] = 1000
        assert replacement.remaining(row) == 0
    finally:
        runtime.close()
