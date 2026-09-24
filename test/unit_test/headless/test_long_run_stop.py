"""Long runs stop on request: the agent loop, computer use and the DAG runner.

A computer-use run (300 s by default) or a DAG could not be stopped once
started, from the GUI or from code, and closing the window then aborted the
process. Each now takes a ``stop_event``; the GUI tabs expose Stop and the
worker registry asks running workers to stop at exit. Fakes only.
"""
import threading

from je_auto_control.utils.agent.agent_loop import AgentBudget, AgentLoop, FakeAgentBackend
from je_auto_control.utils.agent.computer_use import run_computer_use
from je_auto_control.utils.dag.runner import STATUS_SKIPPED, STATUS_SUCCEEDED, run_dag


def _clicks(count):
    return [{"tool": "AC_click_mouse", "input": {}} for _ in range(count)]


def test_the_agent_loop_stops_before_its_next_step():
    stop = threading.Event()
    ran = []

    def runner(tool, args):
        ran.append(tool)
        if len(ran) == 2:
            stop.set()

    loop = AgentLoop(FakeAgentBackend(_clicks(10)), tool_runner=runner,
                     screenshot_fn=lambda: None, budget=AgentBudget(max_steps=10),
                     stop_event=stop)
    result = loop.run("goal")
    assert len(ran) == 2
    assert result.final_message == "stopped" and not result.succeeded


def test_run_computer_use_passes_the_stop_event():
    stop = threading.Event()
    stop.set()
    result = run_computer_use("goal", backend=FakeAgentBackend(_clicks(3)),
                              display_width_px=10, display_height_px=10,
                              stop_event=stop)
    assert result.final_message == "stopped"
    assert result.steps == []


def test_a_stopped_dag_skips_what_has_not_started():
    stop = threading.Event()
    started = []

    def local(node, _definition):
        started.append(node.id)
        stop.set()
        return "ok"

    definition = {"nodes": [
        {"id": "a", "actions": [["AC_x", {}]]},
        {"id": "b", "actions": [["AC_x", {}]], "depends_on": ["a"]},
        {"id": "c", "actions": [["AC_x", {}]], "depends_on": ["b"]},
    ]}
    result = run_dag(definition, max_parallel=1, local_runner=local, stop_event=stop)
    assert started == ["a"]
    assert result.nodes["a"].status == STATUS_SUCCEEDED
    assert [(result.nodes[n].status, result.nodes[n].error) for n in ("b", "c")] == [
        (STATUS_SKIPPED, "stopped")] * 2
    assert not result.succeeded


def test_the_worker_registry_asks_workers_to_stop_at_exit(monkeypatch):
    import pytest
    pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
    from je_auto_control.gui import _worker_thread as registry

    class _Thread:
        def quit(self):
            pass

        def wait(self, _ms):
            return True

    class _Worker:
        stopped = False

        def request_stop(self):
            self.stopped = True

    worker = _Worker()
    monkeypatch.setattr(registry, "_RUNNING", {_Thread(): worker})
    registry._stop_running_threads()  # noqa: SLF001
    assert worker.stopped
