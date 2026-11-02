"""A ChatOps ``/run`` is a stoppable run, and ``/stop`` ends it.

``/run`` used to be stoppable only when the script itself contained an
``AC_run_stoppable`` block: ``AC_stop_execution``, the MCP stop tool and the
GUI's stop-all had nothing to address. The scripts here run fake commands that
wait on the stop-aware ``pause`` -- no input, no screen.
"""
import json
import threading

import pytest

from je_auto_control.utils.chatops import (
    CHATOPS_RUN_PREFIX, CommandRouter, chatops_run_id, cmd_stop,
    register_chatops_default_commands,
)
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.executor.run_control import (
    active_executions, pause, stop_execution, stoppable_run,
)

_WAIT = 10.0
_LONG = 120.0


class _Script:
    """Fake commands: one that waits until it is stopped, one that only marks."""

    def __init__(self):
        self.entered = threading.Event()
        self.after = []
        self.seen_ids = []

    def held(self):
        self.seen_ids.extend(run["run_id"] for run in active_executions())
        self.entered.set()
        pause(_LONG)

    def mark(self):
        self.seen_ids.extend(run["run_id"] for run in active_executions())
        self.after.append("ran")


@pytest.fixture
def script(monkeypatch):
    fake = _Script()
    monkeypatch.setitem(executor.event_dict, "AC_fake_chat_held", fake.held)
    monkeypatch.setitem(executor.event_dict, "AC_fake_chat_mark", fake.mark)
    yield fake
    stop_execution()
    assert active_executions() == [], "a chat run outlived its test"


@pytest.fixture
def root(tmp_path):
    (tmp_path / "long job.json").write_text(
        json.dumps([["AC_fake_chat_held"], ["AC_fake_chat_mark"]]), encoding="utf-8")
    (tmp_path / "quick.json").write_text(json.dumps([["AC_fake_chat_mark"]]), encoding="utf-8")
    return tmp_path


def _router() -> CommandRouter:
    return register_chatops_default_commands(CommandRouter())


class _Background:
    """Dispatch one chat message on another thread and keep its reply."""

    def __init__(self, router, message, context):
        self.reply = None
        self._thread = threading.Thread(
            target=self._run, args=(router, message, context), daemon=True)
        self._thread.start()

    def _run(self, router, message, context):
        self.reply = router.dispatch(message, context=context)

    def result(self):
        self._thread.join(_WAIT)
        assert not self._thread.is_alive(), "the chat run did not end"
        return self.reply


def _chat_runs():
    return [run["run_id"] for run in active_executions()
            if run["run_id"].startswith(CHATOPS_RUN_PREFIX)]


def test_the_run_id_names_the_script_and_is_one_word():
    run_id = chatops_run_id("long job (v2).json")
    assert run_id.startswith("chatops-long_job_v2-")
    assert len(run_id.split()) == 1
    assert chatops_run_id("long job (v2).json") != run_id
    assert chatops_run_id("???.json").startswith("chatops-script-")


def test_a_run_is_listed_while_it_lasts_and_reports_its_id(script, root):
    reply = _router().dispatch("/run quick.json", context={"script_root": str(root)})
    assert reply.succeeded
    assert reply.text == "ran quick.json: 1 action(s) executed"
    assert reply.metadata["run_id"].startswith("chatops-quick-")
    assert script.seen_ids == [reply.metadata["run_id"]]
    assert active_executions() == []


def test_a_bare_stop_all_ends_a_chat_run(script, root):
    run = _Background(_router(), '/run "long job.json"', {"script_root": str(root)})
    assert script.entered.wait(_WAIT)
    (run_id,) = _chat_runs()
    assert run_id.startswith("chatops-long_job-")
    assert stop_execution(reason="stop-all") == 1
    reply = run.result()
    assert reply.text == "run stopped. (stop-all)"
    assert reply.succeeded is False
    assert reply.metadata == {"stopped": True, "run_id": run_id, "reason": "stop-all"}
    assert script.after == [], "the action after the stop still ran"
    assert active_executions() == []


def test_the_stop_command_of_the_executor_ends_it_by_name(script, root):
    run = _Background(_router(), '/run "long job.json"', {"script_root": str(root)})
    assert script.entered.wait(_WAIT)
    (run_id,) = _chat_runs()
    executor.execute_action([["AC_stop_execution", {"run_id": run_id, "reason": "by name"}]])
    assert run.result().text == "run stopped. (by name)"
    assert script.after == []


def test_chat_stop_ends_the_chat_run_and_leaves_other_runs_alone(script, root):
    router = _router()
    run = _Background(router, '/run "long job.json"', {"script_root": str(root)})
    assert script.entered.wait(_WAIT)
    (run_id,) = _chat_runs()
    with stoppable_run("gui-run") as other:
        reply = router.dispatch("/stop", context={"slack_user": "U1"})
        assert reply.succeeded
        assert reply.text == f"stop requested: {run_id}"
        assert reply.metadata["stopped"] == [run_id]
        assert other.stopped is False, "a bare /stop reached a run chat did not start"
    stopped = run.result()
    assert stopped.text == "run stopped. (stopped from chat by U1)"
    assert script.after == []


def test_chat_stop_by_id_reaches_any_run_and_says_so_when_there_is_none(script):
    router = _router()
    with stoppable_run("gui-run") as other:
        nothing = router.dispatch("/stop")
        assert nothing.succeeded is False
        assert nothing.text == ("no chat-started run is in progress. "
                                "Other runs in progress: gui-run (/stop <run-id>).")
        assert other.stopped is False
        missing = router.dispatch("/stop nope")
        assert missing.succeeded is False
        assert missing.text.startswith("no run named 'nope'")
        named = router.dispatch("/stop gui-run")
        assert named.succeeded
        assert named.text == "stop requested: gui-run"
        assert other.stopped
        assert other.reason == "stopped from chat"
    idle = router.dispatch("/stop")
    assert idle.text == "no chat-started run is in progress."
    assert idle.succeeded is False


def test_stop_takes_at_most_one_argument():
    reply = _router().dispatch("/stop a b")
    assert reply.succeeded is False
    assert "usage: /stop [run-id]" in reply.text
    assert cmd_stop([], {}).succeeded is False


def test_inside_a_stoppable_run_the_chat_run_joins_it(script, root):
    """The GUI's Chat-Ops tab wraps the dispatch in its own run; its Stop must still work."""
    router = _router()
    replies = []

    def work():
        with stoppable_run("tab-run"):
            replies.append(router.dispatch('/run "long job.json"',
                                           context={"script_root": str(root)}))

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    assert script.entered.wait(_WAIT)
    assert [run["run_id"] for run in active_executions()] == ["tab-run"]
    assert stop_execution("tab-run", reason="tab stop") == 1
    worker.join(_WAIT)
    assert not worker.is_alive()
    assert replies[0].text == "run stopped. (tab stop)"
    assert replies[0].metadata["run_id"] == "tab-run"


def test_stop_is_listed_in_help():
    text = _router().dispatch("/help").text
    assert "/stop" in text
    assert "/run" in text
