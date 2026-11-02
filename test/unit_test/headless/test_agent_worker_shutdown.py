"""Background shutdown tracks actual workers, including models waiting before input acquisition."""
import threading

from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.jobs import BackgroundTasks
from .test_agent_runtime import FakeTarget, specification


def test_shutdown_cancels_model_initialization_before_any_lease_or_display_page(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import runner
    entered = threading.Event()

    class WaitingModel:
        def __init__(self, _spec):
            operation = current_operation()
            entered.set()
            while not threading.Event().wait(0.01):
                operation.checkpoint()

    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    jobs = BackgroundTasks(runtime)
    runtime.background = jobs
    monkeypatch.setattr(runner, "OllamaTaskBackend", WaitingModel)
    try:
        task = runtime.submit(specification(mode="ollama"))
        jobs.start(task.task_id)
        assert entered.wait(3) and not runtime._leases
        assert runtime.get(task.task_id).state == "queued"
        jobs.close()
        assert runtime.get(task.task_id).state == "cancelled"
        assert not jobs._running and all(not thread.is_alive() for thread in jobs._workers)
    finally:
        jobs.close()
        runtime.close()


def test_unstarted_accepted_work_survives_shutdown_and_late_start_cannot_launch_workers(tmp_path):
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    jobs = BackgroundTasks(runtime)
    try:
        task = runtime.submit(specification(mode="skill", actions=[{"tool": "AC_increment", "arguments": {}}]))
        jobs.close()
        jobs.start(task.task_id)
        assert runtime.get(task.task_id).state == "queued"
        assert jobs._workers == []
    finally:
        jobs.close()
        runtime.close()
