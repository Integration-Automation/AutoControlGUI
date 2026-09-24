"""Config / plumbing defects from the 2026-09-24 audit (no network).

Failure-hook tickets carried secrets to external trackers and one odd backend
stopped the rest; a symlinked plugin outside its directory was imported; the
search index dropped non-ASCII text and ignored capitalised stop words; an
agent-trace field that repeated or extended the record's arguments raised
TypeError; chat commands were case-sensitive and the Slack poller read one page
and died on an ImportError; a NaN counter increment stuck; a warn-level check
failed the diagnostics CLI.
"""
import os

import pytest

from je_auto_control.utils.agent_trace.agent_trace import AgentTrace
from je_auto_control.utils.chatops.router import CommandResult, CommandRouter
from je_auto_control.utils.chatops.slack_bot import SlackBot
from je_auto_control.utils.diagnostics import __main__ as diagnostics_cli
from je_auto_control.utils.failure_hooks.manager import FailureHookManager
from je_auto_control.utils.failure_hooks.report import FailureReport, TicketResult
from je_auto_control.utils.observability.metrics import Counter
from je_auto_control.utils.plugin_loader.plugin_loader import load_plugin_directory
from je_auto_control.utils.search_index.search_index import SearchIndex


class _Backend:
    def __init__(self, name, error=None):
        self.name, self.error, self.bodies = name, error, []

    def create_issue(self, report):
        if self.error is not None:
            raise self.error
        self.bodies.append(report.render_body())
        return TicketResult(backend=self.name, succeeded=True, ticket_id="1")


def test_tickets_are_redacted_and_one_broken_backend_does_not_stop_the_rest():
    manager = FailureHookManager()
    broken, good = _Backend("broken", KeyError("data")), _Backend("good")
    manager.register(broken)
    manager.register(good)
    manager.enable(True)
    token = "ghp_" + "a" * 36
    results = manager.fire(FailureReport(
        source="rest", source_id="1", error_text="failed",
        log_tail=f"Authorization: Bearer {token}", metadata={"password": "hunter2"}))
    assert [result.succeeded for result in results] == [False, True]
    assert token not in good.bodies[0] and "hunter2" not in good.bodies[0]


def test_a_plugin_symlinked_from_outside_is_not_loaded(tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("def AC_evil():\n    return 1\n", encoding="utf-8")
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "good.py").write_text("def AC_good():\n    return 1\n", encoding="utf-8")
    try:
        os.symlink(outside, plugins / "evil.py")
    except (OSError, NotImplementedError):
        pytest.skip("creating symlinks needs a privilege on this machine")
    assert set(load_plugin_directory(str(plugins))) == {"AC_good"}


def test_search_finds_non_ascii_terms_and_folds_stop_words():
    index = SearchIndex(stop_words=["The"])
    index.add("a", "登入 系統")
    index.add("b", "café au lait")
    index.add("c", "the end")
    assert [hit.doc_id for hit in index.search("登入")] == ["a"]
    assert [hit.doc_id for hit in index.search("CAFÉ")] == ["b"]
    assert index.search("the") == []


def test_trace_fields_may_repeat_or_extend_the_record_arguments():
    trace = AgentTrace(clock=lambda: 0.0)
    with trace.operation("chat", model="m1") as fields:
        fields["model"] = "m2"
        fields["cost_usd"] = 0.5
    [span] = trace.spans()
    assert span["attributes"]["cost_usd"] == 0.5


def test_chat_commands_are_case_insensitive():
    router = CommandRouter()
    router.register("help", lambda argv, context: CommandResult(text="ok"))
    assert router.dispatch("/Help").text == "ok"


class _PagedSlack(SlackBot):
    def _api_get(self, method, params):
        if "cursor" not in params:
            return {"messages": [{"ts": "3", "text": "c"}], "has_more": True,
                    "response_metadata": {"next_cursor": "p2"}}
        return {"messages": [{"ts": "2", "text": "b"}, {"ts": "1", "text": "a"}],
                "has_more": False}


def test_the_slack_poller_reads_every_page():
    bot = _PagedSlack(token="xoxb-1", channel_id="C1", router=CommandRouter())
    assert [message["ts"] for message in bot._fetch_messages()] == ["3", "2", "1"]


def test_a_handler_import_error_does_not_end_the_poller(monkeypatch):
    router = CommandRouter()

    def broken(argv, context):
        raise ImportError("no screen backend")

    router.register("shot", broken)
    bot = SlackBot(token="xoxb-1", channel_id="C1", router=router)
    posted = []
    monkeypatch.setattr(bot, "post_message", lambda text, **kwargs: posted.append(text))
    bot._route_one("/shot", {"ts": "1"})
    assert posted


def test_a_nan_increment_is_refused():
    counter = Counter("c_total", "help")
    with pytest.raises(ValueError):
        counter.inc(float("nan"))
    assert counter.value() == 0.0


def test_a_warning_does_not_fail_the_diagnostics_cli(monkeypatch):
    from je_auto_control.utils.diagnostics import diagnostics as diag
    report = diag.DiagnosticsReport(checks=[
        diag.Check(name="mouse", ok=False, severity="warn", detail="no mouse")])
    monkeypatch.setattr(diagnostics_cli, "run_diagnostics", lambda: report)
    assert diagnostics_cli.main([]) == 0
