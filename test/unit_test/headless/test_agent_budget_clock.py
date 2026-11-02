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


def test_concurrent_budget_reads_do_not_mistake_transaction_order_for_clock_rollback(tmp_path):
    """An older caller waiting for SQLite must sample time after the transaction becomes exclusive."""
    from contextlib import contextmanager
    import threading
    from types import SimpleNamespace
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={"fixture": object()})
    waiting, release = threading.Event(), threading.Event()
    result, failures = [], []
    mono = [100.0]

    @contextmanager
    def connection(*, write=False):
        if threading.current_thread().name == "DelayedBudgetReader":
            waiting.set()
            if not release.wait(3):
                raise RuntimeError("budget fixture did not release its waiter")
        with runtime.store.connection(write=write) as value:
            yield value

    try:
        task = runtime.submit({"goal": "budget", "target": "fixture", "allowed_tools": ["AC_fixture"],
            "success_criteria": [{"kind": "result_equals", "key": "ok", "value": True}]})
        runtime.store.start(task.task_id)
        row = runtime.store.get(task.task_id)
        clock = BudgetClock(SimpleNamespace(connection=connection), monotonic=lambda: mono[0],
                            wall=lambda: row["started"])
        assert clock.remaining(row) == 300
        mono[0] = 110

        def read():
            try:
                result.append(clock.remaining(row))
            except Exception as error:
                failures.append(error)

        worker = threading.Thread(target=read, name="DelayedBudgetReader")
        worker.start()
        try:
            assert waiting.wait(2)
            mono[0] = 120
            assert clock.remaining(row) == 280
        finally:
            release.set()
            worker.join(timeout=3)
        assert not worker.is_alive() and not failures
        assert result == [280]
    finally:
        release.set()
        runtime.close()
