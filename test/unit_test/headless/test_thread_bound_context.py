"""Per-thread state stays on the thread that set it, on every build.

The caller a request is served as, the device a matrix worker drives, the
labels a heal event is stamped with and the stop token of a run are kept in
context variables and documented as belonging to the calling thread. A new
thread starts with an empty context on a default build, but with a copy of its
creator's on a free-threaded build and under ``-X thread_inherit_context=1``:
there a scheduler thread first started while an admin's request was being
served kept running as that admin.

As in ``test_execution_scope_threads.py``, every test runs twice: on the
interpreter as it is, and with thread creation forced to inherit the creator's
context, which is what those builds do and works on every supported version.
The last test runs this file under the real flag where the interpreter has it.
Nothing touches a device, the screen or the keyboard.
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

from je_auto_control.utils.executor import run_control
from je_auto_control.utils.executor.run_control import (
    ExecutionStopped, bound_stop_token, checkpoint, current_stop_token, shielded,
    stop_execution, stoppable_run,
)
from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, authorization_scope, current_authorization,
)
from je_auto_control.utils.rbac.deferred import adopted_scope, capture_owner
from je_auto_control.utils.self_healing import locator
from je_auto_control.utils.self_healing.locator import heal_context
from je_auto_control.utils.thread_bound import ThreadBoundVar, thread_marker
from je_auto_control.wrapper.device_context import bound_session, use_device

REPO_ROOT = Path(__file__).resolve().parents[3]
WAIT = 20
_CHILD_ENV = "AC_THREAD_BOUND_CHILD"
_ADMIN = AuthorizationContext(user_id="admin-user", role="admin")


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


def _in_thread(function):
    """Run ``function`` on a new thread and return what it returned."""
    box = {}
    worker = threading.Thread(target=lambda: box.setdefault("value", function()))
    worker.start()
    worker.join(WAIT)
    assert not worker.is_alive()
    return box["value"]


class _Session:
    """Just enough of a ``DeviceSession`` for the binding."""

    platform = "android"
    device_id = "emulator-5554"


# --- the helper ---------------------------------------------------------------------------------

def test_a_value_is_read_back_on_its_thread_and_not_on_another(threads):
    var = ThreadBoundVar("test_thread_bound", "default")
    token = var.set("mine")
    try:
        assert var.get() == "mine"
        assert _in_thread(var.get) == "default"
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(var.get).result(WAIT) == "default"
    finally:
        var.reset(token)
    assert var.get() == "default"


def test_nested_sets_unwind_in_order(threads):
    var = ThreadBoundVar("test_thread_bound_nested", 0)
    outer = var.set(1)
    inner = var.set(2)
    assert var.get() == 2
    var.reset(inner)
    assert var.get() == 1
    var.reset(outer)
    assert var.get() == 0


def test_asyncio_tasks_on_the_binding_thread_see_the_value(threads):
    var = ThreadBoundVar("test_thread_bound_async", "default")

    async def view():
        return var.get()

    async def main():
        return await asyncio.gather(asyncio.create_task(view()), view())

    token = var.set("mine")
    try:
        assert asyncio.run(main()) == ["mine", "mine"]
    finally:
        var.reset(token)


def test_each_thread_has_its_own_marker(threads):
    assert thread_marker() is thread_marker()
    assert _in_thread(thread_marker) is not thread_marker()


# --- who a request is served as -----------------------------------------------------------------

def test_a_thread_started_in_a_request_has_no_caller(threads):
    with authorization_scope(_ADMIN):
        assert current_authorization() is _ADMIN
        assert _in_thread(current_authorization) is None
        assert current_authorization() is _ADMIN, "starting a thread must not disturb the request"
    assert current_authorization() is None


def test_a_daemon_started_in_an_admins_request_does_not_stay_admin(threads):
    request_over, done = threading.Event(), threading.Event()
    seen = []

    def daemon():
        request_over.wait(WAIT)
        seen.append(current_authorization())
        # Deferred work with no owner of its own must not pick the admin up either.
        with adopted_scope(None):
            seen.append(current_authorization())
        seen.append(capture_owner())
        done.set()

    with authorization_scope(_ADMIN):
        threading.Thread(target=daemon, daemon=True).start()
    request_over.set()
    assert done.wait(WAIT)
    assert seen == [None, None, None]


def test_a_caller_handed_over_on_purpose_is_served_on_the_other_thread(threads):
    def branch():
        with authorization_scope(_ADMIN):
            return current_authorization()

    assert _in_thread(branch) is _ADMIN


# --- which device a worker drives ---------------------------------------------------------------

def test_a_thread_started_inside_use_device_does_not_reach_the_device(threads):
    session = _Session()
    with use_device(session):
        assert bound_session("android") is session
        assert _in_thread(lambda: bound_session("android")) is None
        assert bound_session("android", "emulator-5554") is session
    assert bound_session("android") is None


def test_two_workers_each_see_their_own_device(threads):
    first, second = _Session(), _Session()
    ready, release = threading.Barrier(2), threading.Event()
    seen = {}

    def worker(name, session):
        with use_device(session):
            ready.wait(WAIT)
            release.wait(WAIT)
            seen[name] = bound_session("android")

    workers = [threading.Thread(target=worker, args=("a", first)),
               threading.Thread(target=worker, args=("b", second))]
    for thread in workers:
        thread.start()
    release.set()
    for thread in workers:
        thread.join(WAIT)
    assert seen == {"a": first, "b": second}


# --- what a heal event is stamped with ----------------------------------------------------------

def test_a_thread_started_in_a_heal_context_is_not_stamped_with_it(threads):
    with heal_context(run_id="run-1", step_id="s1"):
        assert dict(locator._context.get()) == {"run_id": "run-1", "step_id": "s1"}
        assert dict(_in_thread(locator._context.get)) == {}
        with heal_context(locator_id="ok-button"):
            assert dict(locator._context.get()) == {
                "run_id": "run-1", "step_id": "s1", "locator_id": "ok-button"}
    assert dict(locator._context.get()) == {}


# --- which stop a run answers to ----------------------------------------------------------------

def test_a_thread_started_in_a_stoppable_run_is_not_part_of_it(threads):
    with stoppable_run("bound-run") as token:
        assert current_stop_token() is token
        assert _in_thread(current_stop_token) is None


def test_a_daemon_started_in_a_stopped_run_is_not_stopped_for_ever(threads):
    run_over, done = threading.Event(), threading.Event()
    outcome = []

    def daemon():
        run_over.wait(WAIT)
        try:
            checkpoint()
            run_control.pause(0)
            outcome.append("alive")
        except ExecutionStopped:
            outcome.append("stopped")
        # ...and its own "stop every other run" spares nothing by mistake.
        outcome.append(stop_execution())
        done.set()

    with stoppable_run("bound-stopped") as token:
        threading.Thread(target=daemon, daemon=True).start()
        token.stop("over")
    run_over.set()
    assert done.wait(WAIT)
    assert outcome == ["alive", 0]


def test_a_branch_given_the_token_stops_with_the_run(threads):
    def branch(token):
        with bound_stop_token(token):
            try:
                checkpoint()
            except ExecutionStopped as error:
                return error.run_id
        return None

    with stoppable_run("bound-branch") as token:
        token.stop()
        assert _in_thread(lambda: branch(token)) == "bound-branch"


def test_a_shield_does_not_follow_a_thread_started_inside_it(threads):
    def branch(token):
        with bound_stop_token(token):
            try:
                checkpoint()
            except ExecutionStopped:
                return "stopped"
        return "shielded"

    with stoppable_run("bound-shield") as token:
        token.stop()
        with shielded():
            checkpoint()  # this thread's cleanup may finish
            assert _in_thread(lambda: branch(token)) == "stopped"


# --- the real flag ------------------------------------------------------------------------------

@pytest.mark.skipif(not hasattr(sys.flags, "thread_inherit_context"),
                    reason="-X thread_inherit_context exists from Python 3.14")
@pytest.mark.skipif(bool(os.environ.get(_CHILD_ENV)), reason="already the child run")
def test_these_tests_pass_with_real_context_inheritance():
    """The interpreter's own inheritance, not the emulation: what a free-threaded build does."""
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT), **{_CHILD_ENV: "1"})
    done = subprocess.run(  # nosec B603  # nosemgrep  # reason: this interpreter, this test file, no shell
        [sys.executable, "-X", "thread_inherit_context=1", "-m", "pytest", "-q",
         "-p", "no:cacheprovider", str(Path(__file__))],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300, check=False)
    assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
    assert " passed" in done.stdout
    assert " failed" not in done.stdout
