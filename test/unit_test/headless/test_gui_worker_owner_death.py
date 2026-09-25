"""A worker thread outlives the tab that started it (offscreen, subprocess).

``start_worker`` parented the ``QThread`` to the tab, so closing the tab or the
window while the work still ran destroyed a running ``QThread`` — which aborts
the process — and interpreter exit did the same to any thread still up. Each
case runs in a child interpreter so the old abort fails the test rather than
the suite.
"""
import os
import subprocess  # nosec B404  # reason: runs this test's own probe script
import textwrap
import time

import pytest

from headless._exit_probe import exit_seconds, run_probe

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

_PROBE = textwrap.dedent("""
    import os, sys, time
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import QEvent, QObject, Signal
    from PySide6.QtWidgets import QApplication, QWidget
    from je_auto_control.gui import _worker_thread as wt

    class Worker(QObject):
        finished = Signal(object)

        def run(self):
            # "stuck": one step far longer than exit's grace, with no way to
            # stop it -- a slow LLM request.
            time.sleep(60 if sys.argv[1] == "stuck" else 0.5)
            self.finished.emit(1)

    calls = []
    app = QApplication([])
    owner = QWidget()
    wt.start_worker(owner, Worker(), on_done=calls.append,
                    on_thread_done=lambda: calls.append("thread done"))
    time.sleep(0.1)
    owner.deleteLater()
    del owner
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    if sys.argv[1] == "wait":
        deadline = time.monotonic() + 10
        while wt.running_threads() and time.monotonic() < deadline:
            app.processEvents()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
            time.sleep(0.02)
        print("left", wt.running_threads(), "calls", calls)
    else:
        wt._EXIT_GRACE_S = 0.5
        print("exiting", time.time(), flush=True)
""")


def _run_probe(mode: str) -> subprocess.CompletedProcess:
    return run_probe(_PROBE, mode)


def test_destroying_the_owner_mid_run_neither_aborts_nor_calls_back():
    done = _run_probe("wait")
    assert done.returncode == 0, done.stderr
    # The thread finished and was deleted; the dead tab heard nothing.
    assert "left 0 calls []" in done.stdout


def test_exiting_while_a_worker_runs_lets_it_finish():
    done = _run_probe("exit")
    assert done.returncode == 0, done.stderr
    assert "exiting" in done.stdout


def test_exiting_during_a_step_longer_than_the_grace_still_exits_cleanly():
    done = _run_probe("stuck")
    # Destroying the running QThread at exit aborted here; a daemon thread
    # just ends with the process once the grace is over -- well before its
    # 60 s step would.
    assert done.returncode == 0, done.stderr
    assert exit_seconds(done) < 30


def _pump_until(app, predicate, seconds=10.0):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    return predicate()


@pytest.mark.parametrize("which", ["computer_use", "dag", "llm_planner"])
def test_the_tabs_run_their_job_and_clear_the_guard(monkeypatch, which):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    seen = []
    if which == "computer_use":
        from je_auto_control.gui import computer_use_tab as mod
        monkeypatch.setattr(mod, "run_computer_use", lambda **kw: seen.append(kw["goal"]) or "r")
        monkeypatch.setattr(mod, "result_to_dict", lambda result: {"succeeded": True})
        tab = mod.ComputerUseTab()
        tab._spawn_worker({"goal": "g"})  # noqa: SLF001
        guard = "_thread"
    elif which == "dag":
        from je_auto_control.gui import dag_tab as mod

        def failing_run(definition, max_parallel, stop_event=None):
            seen.append(definition)
            raise RuntimeError("stop")

        monkeypatch.setattr(mod, "run_dag", failing_run)
        tab = mod.DagTab()
        tab._spawn_worker({"nodes": []})  # noqa: SLF001
        guard = "_thread"
    else:
        from je_auto_control.gui import llm_planner_tab as mod
        monkeypatch.setattr(mod, "plan_actions", lambda *a, **kw: seen.append("plan") or [["AC_x", {}]])
        tab = mod.LLMPlannerTab()
        tab._description.setPlainText("do it")  # noqa: SLF001
        tab._on_plan()  # noqa: SLF001
        guard = "_plan_thread"
    assert getattr(tab, guard) is not None
    assert _pump_until(app, lambda: getattr(tab, guard) is None), "the guard never cleared"
    assert seen
    tab.deleteLater()
