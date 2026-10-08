"""A run's variable scope stays on the thread that opened it, on every build.

``execution_scope`` binds through a ``ContextVar``, and its contract is that a
thread started inside the block does not inherit the binding: ``AC_parallel``
branches fork the variables into executors of their own, the DAG runner
re-binds the scope explicitly, and every other thread -- a scheduler, an
observer, a timer -- keeps the process scope.

That used to be a property of the interpreter rather than of the code. A new
thread starts with an empty context on a default build, but with a copy of its
creator's on a free-threaded build and under ``-X thread_inherit_context=1``.
Measured on CPython 3.14.8t and on 3.14.7 with the flag: a thread started in a
run saw the run's scope, and went on writing into it after the run had ended.

Every test here runs twice: on the interpreter as it is, and with thread
creation forced to inherit the creator's context, which is what those builds
do and works on every supported version. The last test runs this file and the
two older scope files under the real flag where the interpreter has it.

Nothing touches the mouse, keyboard or screen: only variable commands and
probes registered for the test are run.
"""
import asyncio
import contextvars
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from je_auto_control.utils.executor.action_executor import execute_action, executor
from je_auto_control.utils.script_vars import execution_scope
from je_auto_control.utils.script_vars.execution import (
    bound_scope, current_scope, run_level_scope,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROBE = "AC_scope_thread_probe"
WAIT = 20
_CHILD_ENV = "AC_SCOPE_THREADS_CHILD"


@pytest.fixture(params=["native", "inheriting"])
def threads(request, monkeypatch):
    """How new threads get their context: the interpreter's way, or copied from the creator."""
    if request.param == "inheriting":
        start = threading.Thread.start

        def start_in_creators_context(self):
            context, run = contextvars.copy_context(), self.run
            self.run = lambda: context.run(run)
            start(self)

        monkeypatch.setattr(threading.Thread, "start", start_in_creators_context)
    return request.param


@pytest.fixture
def process_scope():
    """The module executor's own scope, emptied for the test and restored after it."""
    saved = executor.variables.as_dict()
    executor.variables.clear()
    yield executor.variables
    executor.event_dict.pop(PROBE, None)
    executor.variables.clear()
    executor.variables.update_many(saved)


def _in_thread(function):
    """Run ``function`` on a new thread and return what it returned."""
    box = {}
    worker = threading.Thread(target=lambda: box.setdefault("value", function()))
    worker.start()
    worker.join(WAIT)
    assert not worker.is_alive()
    return box["value"]


def _view():
    """What the calling thread sees: (is a run bound, the module executor's ``who``)."""
    return current_scope() is not None, executor.variables.as_dict().get("who")


def test_a_thread_started_in_a_run_keeps_the_process_scope(threads, process_scope):
    process_scope.set("who", "process")
    with execution_scope({"who": "run"}) as scope:
        assert _view() == (True, "run")
        assert _in_thread(_view) == (False, "process")
        assert current_scope() is scope, "starting a thread must not disturb the run"


def test_pool_workers_and_timers_keep_the_process_scope(threads, process_scope):
    process_scope.set("who", "process")
    fired = []
    with execution_scope({"who": "run"}):
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert pool.submit(_view).result(WAIT) == (False, "process")
        timer = threading.Timer(0.01, lambda: fired.append(_view()))
        timer.start()
        timer.join(WAIT)
    assert fired == [(False, "process")]


def test_a_thread_outliving_its_run_writes_to_the_process_scope(threads, process_scope):
    run_over, done = threading.Event(), threading.Event()

    def daemon():
        run_over.wait(WAIT)
        execute_action([["AC_set_var", {"name": "late", "value": 1}]])
        done.set()

    with execution_scope({"who": "run"}) as scope:
        worker = threading.Thread(target=daemon, daemon=True)
        worker.start()
    run_over.set()
    assert done.wait(WAIT)
    worker.join(WAIT)
    assert scope.as_dict() == {"who": "run"}, "the ended run's scope was written to"
    assert process_scope.as_dict() == {"late": 1}


def test_a_thread_started_in_a_run_can_open_a_run_of_its_own(threads, process_scope):
    def nested():
        before = _view()
        with execution_scope({"who": "thread"}):
            inside = _view()
        return before, inside, _view()

    with execution_scope({"who": "run"}):
        assert _in_thread(nested) == ((False, None), (True, "thread"), (False, None))
        assert _view() == (True, "run")


def test_run_level_scope_on_such_a_thread_does_not_join_the_run(threads, process_scope):
    def as_its_own_run():
        with run_level_scope() as scope:
            scope.set("who", "thread")
            return scope

    with execution_scope({"who": "run"}) as scope:
        assert _in_thread(as_its_own_run) is not scope
        with run_level_scope() as joined:
            assert joined is scope
        assert scope.as_dict() == {"who": "run"}


def test_a_captured_scope_can_still_be_rebound_on_a_worker(threads, process_scope):
    def on_behalf_of_the_run(scope):
        with bound_scope(scope):
            execute_action([["AC_set_var", {"name": "from_worker", "value": 1}]])
            inside = current_scope() is scope
        return inside, current_scope()

    with execution_scope({"who": "run"}) as scope:
        assert _in_thread(lambda: on_behalf_of_the_run(scope)) == (True, None)
        assert scope.as_dict() == {"who": "run", "from_worker": 1}
    assert process_scope.as_dict() == {}


def test_parallel_branches_fork_instead_of_joining_the_run(threads, process_scope):
    seen = []
    executor.event_dict[PROBE] = lambda value=None: seen.append(
        (value, current_scope() is not None)) or value
    with execution_scope({"who": "run"}) as scope:
        record = execute_action([["AC_parallel", {"branches": [
            [[PROBE, {"value": "${who}"}], ["AC_set_var", {"name": "who", "value": "left"}],
             [PROBE, {"value": "${who}"}]],
            [[PROBE, {"value": "${who}"}], ["AC_set_var", {"name": "right_only", "value": 1}]],
        ]}]])
        assert scope.as_dict() == {"who": "run"}, record
    assert sorted(seen) == [("left", False), ("run", False), ("run", False)], record
    assert process_scope.as_dict() == {}


def test_tasks_on_the_binding_thread_share_the_run(threads, process_scope):
    async def main():
        return await asyncio.gather(asyncio.create_task(view()), view())

    async def view():
        return _view()

    with execution_scope({"who": "run"}):
        assert asyncio.run(main()) == [(True, "run"), (True, "run")]


@pytest.mark.skipif(not hasattr(sys.flags, "thread_inherit_context"),
                    reason="-X thread_inherit_context exists from Python 3.14")
@pytest.mark.skipif(bool(os.environ.get(_CHILD_ENV)), reason="already the child run")
def test_the_scope_tests_pass_with_real_context_inheritance():
    """The interpreter's own inheritance, not the emulation: what a free-threaded build does."""
    here = Path(__file__).parent
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT), **{_CHILD_ENV: "1"})
    done = subprocess.run(  # nosec B603  # nosemgrep  # reason: this interpreter, repository test files, no shell
        [sys.executable, "-X", "thread_inherit_context=1", "-m", "pytest", "-q",
         "-p", "no:cacheprovider", str(Path(__file__)),
         str(here / "test_execution_scope_isolation.py"),
         str(here / "test_scope_run_level_callers.py")],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300, check=False)
    assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
    assert " passed" in done.stdout and " failed" not in done.stdout
