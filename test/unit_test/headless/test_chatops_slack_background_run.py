"""A ``/stop`` posted to Slack is read while the bot's own ``/run`` is going.

``SlackBot.poll_once`` dispatched every command on the poll thread, so the
``/stop`` meant for a run was fetched only after that run had ended. ``/run``
now executes on a worker thread, one at a time per bot, and the poll loop keeps
reading.

Slack is a fake held in memory -- no network. The scripts run fake commands
that wait on the stop-aware ``pause``: no input, no screen. Every wait is
bounded and none is asserted to be short.
"""
import json
import threading

import pytest

from je_auto_control.utils.chatops import (
    CHATOPS_RUN_PREFIX, CommandResult, CommandRouter, SlackBot, SlackError,
    register_chatops_default_commands,
)
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.executor.run_control import (
    active_executions, pause, stop_execution,
)

_WAIT = 10.0
_LONG = 120.0
_WORKER_PREFIX = "chatops-slack-"


class _FakeSlack:
    """The two Slack calls the bot makes, answered from memory."""

    def __init__(self):
        self._changed = threading.Condition()
        self._pending = []
        self.posts = []
        self.post_threads = []
        self.fail_posts_from_workers = False

    def say(self, ts, text, user="U1"):
        with self._changed:
            self._pending.append({"ts": str(ts), "user": user, "text": text})

    def api_get(self, method, _params):
        if method == "auth.test":
            return {"ok": True, "user_id": "U_BOT"}
        with self._changed:
            batch = list(reversed(self._pending))  # Slack answers newest first
            self._pending.clear()
        return {"ok": True, "messages": batch}

    def api_post(self, _method, payload):
        thread = threading.current_thread()
        if self.fail_posts_from_workers and thread.name.startswith(_WORKER_PREFIX):
            raise SlackError("reply failed")
        with self._changed:
            self.posts.append(payload)
            self.post_threads.append(thread)
            self._changed.notify_all()
        return {"ok": True}

    def wait_for_posts(self, count):
        with self._changed:
            return self._changed.wait_for(lambda: len(self.posts) >= count, _WAIT)

    def texts(self):
        with self._changed:
            return [post["text"] for post in self.posts]


class _Script:
    """Fake commands: one that waits until it is stopped, one that only marks."""

    def __init__(self):
        self.entered = threading.Event()
        self.threads = []
        self.after = []

    def held(self):
        self.threads.append(threading.current_thread())
        self.entered.set()
        pause(_LONG)

    def mark(self):
        self.threads.append(threading.current_thread())
        self.after.append("ran")


def _workers():
    return [thread for thread in threading.enumerate()
            if thread.name.startswith(_WORKER_PREFIX) and thread.is_alive()]


@pytest.fixture()
def script(monkeypatch):
    fake = _Script()
    monkeypatch.setitem(executor.event_dict, "AC_fake_slack_held", fake.held)
    monkeypatch.setitem(executor.event_dict, "AC_fake_slack_mark", fake.mark)
    yield fake
    stop_execution()


@pytest.fixture()
def root(tmp_path, monkeypatch):
    (tmp_path / "long job.json").write_text(
        json.dumps([["AC_fake_slack_held"], ["AC_fake_slack_mark"]]), encoding="utf-8")
    (tmp_path / "quick.json").write_text(json.dumps([["AC_fake_slack_mark"]]), encoding="utf-8")
    monkeypatch.setenv("JE_AUTOCONTROL_CHATOPS_SCRIPT_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture()
def slack():
    return _FakeSlack()


@pytest.fixture()
def bot(slack, script, root, monkeypatch):
    """A bot with the default commands whose Slack calls go to the fake."""
    made = _make_bot(slack, monkeypatch, register_chatops_default_commands(CommandRouter()))
    yield made
    made.stop(timeout=_WAIT)
    stop_execution()
    for worker in _workers():
        worker.join(_WAIT)
    assert _workers() == [], "a worker outlived its test"
    assert active_executions() == [], "a chat run outlived its test"


def _make_bot(slack, monkeypatch, router, **options):
    made = SlackBot(token="xoxb-fake", channel_id="C1", router=router,
                    poll_interval_s=1.0, **options)
    monkeypatch.setattr(made, "_api_get", slack.api_get)
    monkeypatch.setattr(made, "_api_post", slack.api_post)
    return made


class _Poll:
    """One ``poll_once`` on its own thread, so a poll that blocks fails instead of hanging."""

    def __init__(self, bot):
        self.count = None
        self.error = None
        self.thread = threading.Thread(target=self._run, args=(bot,), daemon=True)
        self.thread.start()
        self.thread.join(_WAIT)
        assert not self.thread.is_alive(), "poll_once waited for the command it dispatched"
        if self.error is not None:
            raise self.error

    def _run(self, bot):
        try:
            self.count = bot.poll_once()
        except SlackError as error:
            self.error = error


def _start_long_run(bot, slack, script, ts=1):
    slack.say(ts, '/run "long job.json"')
    poll = _Poll(bot)
    assert poll.count == 1
    assert script.entered.wait(_WAIT)
    run_id = bot.running_run_id
    assert run_id is not None and run_id.startswith(f"{CHATOPS_RUN_PREFIX}long_job-")
    return poll, run_id


# --- the run is on another thread ------------------------------------------

def test_a_run_executes_on_a_worker_and_the_poll_returns(bot, slack, script):
    poll, run_id = _start_long_run(bot, slack, script)
    assert script.threads[0] is not poll.thread
    assert script.threads[0].name == f"{_WORKER_PREFIX}{run_id}"
    assert [run["run_id"] for run in active_executions()] == [run_id]
    assert slack.texts() == [], "the reply comes when the run ends, not when it starts"
    assert bot.last_seen_ts == "1"


def test_a_quick_run_replies_from_the_worker_in_the_message_thread(bot, slack, script):
    slack.say(5, "/run quick.json")
    assert _Poll(bot).count == 1
    assert slack.wait_for_posts(1)
    assert slack.posts == [{"channel": "C1", "thread_ts": "5",
                            "text": "ran quick.json: 1 action(s) executed"}]
    assert slack.post_threads[0].name.startswith(_WORKER_PREFIX)
    assert script.after == ["ran"]


# --- /stop reaches it --------------------------------------------------------

def test_stop_arrives_while_the_run_is_blocked_and_ends_it(bot, slack, script):
    _poll, run_id = _start_long_run(bot, slack, script)
    slack.say(2, "/stop", user="U7")
    stopping = _Poll(bot)
    assert stopping.count == 1
    assert slack.wait_for_posts(2)
    assert slack.posts == [
        {"channel": "C1", "thread_ts": "2", "text": f"stop requested: {run_id}"},
        {"channel": "C1", "thread_ts": "1",
         "text": "run stopped. (stopped from chat by U7)"},
    ]
    assert slack.post_threads[0] is stopping.thread, "/stop is answered on the poll thread"
    assert slack.post_threads[1].name == f"{_WORKER_PREFIX}{run_id}"
    assert script.after == [], "the action after the stop still ran"
    assert bot.stop(timeout=_WAIT) is True
    assert bot.running_run_id is None


def test_a_stop_in_the_same_batch_as_its_run_still_finds_it(bot, slack, script):
    """``/run`` is registered before the next message is read, however the threads fall."""
    slack.say(1, '/run "long job.json"')
    slack.say(2, "/stop")
    assert _Poll(bot).count == 2
    assert slack.wait_for_posts(2)
    texts = slack.texts()
    assert texts[0].startswith(f"stop requested: {CHATOPS_RUN_PREFIX}long_job-")
    assert texts[1] == "run stopped. (stopped from chat by U1)"
    assert script.after == []


def test_stop_by_id_and_stop_of_an_unknown_run_answer_at_once(bot, slack, script):
    _poll, run_id = _start_long_run(bot, slack, script)
    slack.say(2, "/stop nope")
    _Poll(bot)
    assert slack.texts() == [f"no run named 'nope' is in progress. "
                             f"Other runs in progress: {run_id} (/stop <run-id>)."]
    assert bot.running_run_id == run_id
    slack.say(3, f"/stop {run_id}")
    _Poll(bot)
    assert slack.wait_for_posts(3)
    assert slack.texts()[1:] == [f"stop requested: {run_id}",
                                 "run stopped. (stopped from chat by U1)"]


# --- one run per bot ---------------------------------------------------------

def test_a_second_run_is_refused_while_one_is_going(bot, slack, script):
    _poll, run_id = _start_long_run(bot, slack, script)
    slack.say(2, "/run quick.json")
    refused = _Poll(bot)
    assert refused.count == 1
    assert slack.posts == [{
        "channel": "C1", "thread_ts": "2",
        "text": f"run: already running ({run_id}); wait for it to end or /stop it first.",
    }]
    assert slack.post_threads[0] is refused.thread
    assert script.after == [], "the refused run executed"
    assert len(_workers()) == 1
    assert bot.running_run_id == run_id


def test_a_run_is_accepted_again_once_the_first_has_ended(bot, slack, script):
    _start_long_run(bot, slack, script)
    slack.say(2, "/stop")
    _Poll(bot)
    assert slack.wait_for_posts(2)
    assert bot.wait_idle(timeout=_WAIT) is True
    assert bot.running_run_id is None
    slack.say(3, "/run quick.json")
    assert _Poll(bot).count == 1
    assert slack.wait_for_posts(3)
    assert slack.texts()[2] == "ran quick.json: 1 action(s) executed"
    assert script.after == ["ran"]


def test_wait_idle_does_not_stop_the_run(bot, slack, script):
    _poll, run_id = _start_long_run(bot, slack, script)
    assert bot.wait_idle(timeout=0.2) is False
    assert bot.running_run_id == run_id and slack.texts() == []


# --- the other commands stay where they were ---------------------------------

def test_other_commands_are_answered_on_the_poll_thread_during_a_run(bot, slack, script):
    _poll, run_id = _start_long_run(bot, slack, script)
    slack.say(2, "/help")
    slack.say(3, "/scripts")
    asked = _Poll(bot)
    assert asked.count == 2
    texts = slack.texts()
    assert len(texts) == 2, "both replies were posted before poll_once returned"
    assert texts[0].startswith("Available commands:") and texts[1].startswith("scripts under")
    assert all(thread is asked.thread for thread in slack.post_threads)
    assert bot.running_run_id == run_id


def test_a_command_that_cannot_be_parsed_is_still_answered(bot, slack):
    slack.say(1, '/run "unclosed')
    assert _Poll(bot).count == 0
    assert slack.texts()[0].startswith("router error: could not parse command")
    assert _workers() == []


def test_only_the_listed_commands_run_in_the_background(slack, script, root, monkeypatch):
    seen = []
    router = CommandRouter()

    def deploy(_argv, _context):
        seen.append(threading.current_thread())
        script.entered.set()
        pause(_LONG)
        return CommandResult(text="deployed")

    def ping(_argv, _context):
        seen.append(threading.current_thread())
        return CommandResult(text="pong")

    router.register("deploy", deploy)
    router.register("ping", ping)
    register_chatops_default_commands(router)
    made = _make_bot(slack, monkeypatch, router, background_commands=frozenset({"Deploy"}))
    try:
        slack.say(1, "/deploy site")
        slack.say(2, "/ping")
        poll = _Poll(made)
        assert poll.count == 2
        assert script.entered.wait(_WAIT)
        assert made.background_commands == frozenset({"deploy"})
        # The two handlers run on different threads, so their order is not fixed.
        assert len(seen) == 2 and poll.thread in seen
        assert [thread.name.startswith(_WORKER_PREFIX) for thread in seen].count(True) == 1
        assert (made.running_run_id or "").startswith(f"{CHATOPS_RUN_PREFIX}site-")
        slack.say(3, "/stop")
        _Poll(made)
        assert slack.wait_for_posts(3)
        assert slack.texts()[2] == "deploy stopped. (stopped from chat by U1)"
    finally:
        assert made.stop(timeout=_WAIT) is True


# --- shutdown ----------------------------------------------------------------

def test_stopping_the_bot_stops_the_run_and_joins_the_worker(bot, slack, script):
    _poll, run_id = _start_long_run(bot, slack, script)
    worker = script.threads[0]
    assert bot.stop(timeout=_WAIT) is True
    assert not worker.is_alive()
    assert _workers() == []
    assert slack.posts == [{"channel": "C1", "thread_ts": "1",
                            "text": "run stopped. (the bot was stopped)"}]
    assert script.after == []
    assert active_executions() == []
    assert bot.running_run_id is None
    assert bot.stop(timeout=_WAIT) is True, "stopping twice is harmless"


def test_a_stopped_bot_refuses_a_run_instead_of_starting_a_worker(bot, slack, script):
    bot.stop(timeout=_WAIT)
    slack.say(1, "/run quick.json")
    assert _Poll(bot).count == 1
    assert slack.texts() == ["run: the bot is stopping; not started."]
    assert _workers() == [] and script.after == []


def test_run_forever_keeps_reading_during_a_run_and_stop_ends_both(bot, slack, script):
    slack.say(1, '/run "long job.json"')
    loop = threading.Thread(target=bot.run_forever, daemon=True)
    loop.start()
    assert script.entered.wait(_WAIT)
    slack.say(2, "/stop")
    assert slack.wait_for_posts(2), "the loop did not read /stop while the run was going"
    assert slack.texts()[1] == "run stopped. (stopped from chat by U1)"
    assert bot.stop(timeout=_WAIT) is True
    loop.join(_WAIT)
    assert not loop.is_alive()


# --- a reply that cannot be posted -------------------------------------------

def test_a_failed_reply_from_the_worker_does_not_rerun_or_end_the_bot(bot, slack, script):
    slack.fail_posts_from_workers = True
    slack.say(1, "/run quick.json")
    assert _Poll(bot).count == 1
    assert bot.wait_idle(timeout=_WAIT) is True
    assert script.after == ["ran"], "the command ran exactly once"
    assert slack.texts() == []
    slack.fail_posts_from_workers = False
    slack.say(2, "/help")
    assert _Poll(bot).count == 1
    assert bot.last_seen_ts == "2"
    assert script.after == ["ran"]
