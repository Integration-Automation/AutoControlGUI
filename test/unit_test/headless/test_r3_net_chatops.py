"""Round-3 net audit: chat-ops must reply on failure, never kill the poller.

An in-flight run's ``None`` duration made ``/status`` raise TypeError; the
router did not catch framework/DB errors; and a transient reply failure could
re-execute an already-run command because ``last_seen_ts`` was only committed
after the whole batch. All three would silently stop ``run_forever``.
"""
import sqlite3

import pytest

from je_auto_control.utils.chatops import handlers
from je_auto_control.utils.chatops.router import CommandResult, CommandRouter
from je_auto_control.utils.chatops.slack_bot import SlackBot, SlackError
from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException,
)
from je_auto_control.utils.run_history.history_store import RunRecord


# --- finding 10a: None duration in /status --------------------------------

def test_cmd_status_handles_in_flight_none_duration(monkeypatch):
    row = RunRecord(
        id=1, source_type="scheduler", source_id="j1", script_path="s.json",
        started_at=100.0, finished_at=None, status="running", error_text=None)

    class FakeStore:
        def list_runs(self, limit=5):
            return [row]

    monkeypatch.setattr(
        "je_auto_control.utils.run_history.history_store."
        "default_history_store", FakeStore())

    result = handlers.cmd_status([], {})  # must not raise TypeError
    assert "in progress" in result.text


# --- finding 10b: router contains framework / DB errors -------------------

def test_router_returns_reply_on_framework_exc():
    router = CommandRouter()

    def boom(_argv, _ctx):
        raise AutoControlActionException("script blew up")

    router.register("run", boom)
    result = router.dispatch("/run x")

    assert result is not None
    assert result.succeeded is False
    assert "run failed" in result.text


def test_router_returns_reply_on_db_error():
    router = CommandRouter()

    def boom(_argv, _ctx):
        raise sqlite3.OperationalError("database is locked")

    router.register("status", boom)
    result = router.dispatch("/status")

    assert result is not None
    assert result.succeeded is False


# --- finding 10c: slack_bot commits last_seen_ts per message --------------

def test_last_seen_ts_committed_before_reply(monkeypatch):
    """A reply-post failure must not cause the command to run twice."""
    executed: list = []
    router = CommandRouter()

    def do_run(_argv, _ctx):
        executed.append(1)
        return CommandResult(text="ran")

    router.register("run", do_run)
    bot = SlackBot(token="xoxb-test", channel_id="C1", router=router)

    # Slack returns newest-first; only the older message ("1") is reached
    # before the reply fails.
    monkeypatch.setattr(bot, "_fetch_messages", lambda: [
        {"ts": "2", "text": "/run a", "user": "U1"},
        {"ts": "1", "text": "/run b", "user": "U1"},
    ])
    monkeypatch.setattr(bot, "_is_self", lambda msg: False)

    def failing_post(_text, *, thread_ts=""):
        raise SlackError("reply failed")

    monkeypatch.setattr(bot, "post_message", failing_post)

    with pytest.raises(SlackError):
        bot.poll_once()

    # The command ran once and its ts was committed *before* the reply, so the
    # next poll (Slack's `oldest` is exclusive) will not re-run it.
    assert executed == [1]
    assert bot.last_seen_ts == "1"
