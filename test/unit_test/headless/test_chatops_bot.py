"""Tests for the chat-ops router, default handlers, and Slack adapter."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from je_auto_control.utils.chatops import (
    ChatOpsError, CommandResult, CommandRouter, SlackBot, SlackError,
)
from je_auto_control.utils.chatops.handlers import (
    cmd_run, cmd_scripts, cmd_screenshot, cmd_status,
)


# === router =================================================================

@pytest.fixture
def router() -> CommandRouter:
    return CommandRouter()


def test_router_rejects_blank_prefix():
    with pytest.raises(ChatOpsError):
        CommandRouter(prefix="")


def test_router_register_normalises_name(router):
    spec = router.register("ECHO", lambda argv, ctx: CommandResult(text="x"))
    assert spec.name == "echo"


def test_router_register_rejects_whitespace(router):
    with pytest.raises(ChatOpsError):
        router.register("bad name", lambda argv, ctx: CommandResult(text=""))


def test_router_register_rejects_blank_name(router):
    with pytest.raises(ChatOpsError):
        router.register("   ", lambda argv, ctx: CommandResult(text=""))


def test_parse_returns_none_for_non_command(router):
    assert router.parse("hello world") is None


def test_parse_returns_none_for_bare_prefix(router):
    assert router.parse("/") is None


def test_parse_tokenises_quoted_args(router):
    assert router.parse('/run "two words"') == ["run", "two words"]


def test_parse_raises_chatops_error_on_bad_quotes(router):
    with pytest.raises(ChatOpsError):
        router.parse('/run "unterminated')


def test_dispatch_returns_none_for_non_command(router):
    assert router.dispatch("hello") is None


def test_dispatch_routes_to_registered_handler(router):
    router.register(
        "ping", lambda argv, ctx: CommandResult(text="pong"),
    )
    result = router.dispatch("/ping")
    assert result is not None
    assert result.text == "pong"


def test_dispatch_unknown_command_returns_failure(router):
    result = router.dispatch("/garbage")
    assert result is not None
    assert result.succeeded is False
    assert "unknown command" in result.text


def test_dispatch_help_lists_registered_commands(router):
    router.register(
        "ping", lambda argv, ctx: CommandResult(text="pong"),
        description="reply with pong",
    )
    result = router.dispatch("/help")
    assert result is not None
    assert "/ping" in result.text


def test_dispatch_handler_chatops_error_returns_failure(router):
    def bad(_argv, _ctx):
        raise ChatOpsError("forced bad input")

    router.register("bad", bad)
    result = router.dispatch("/bad")
    assert result is not None
    assert result.succeeded is False
    assert "forced bad input" in result.text


def test_dispatch_handler_runtime_error_returns_failure(router):
    def boom(_argv, _ctx):
        raise RuntimeError("kaboom")

    router.register("boom", boom)
    result = router.dispatch("/boom")
    assert result is not None
    assert result.succeeded is False
    assert "kaboom" in result.text


def test_role_required_blocks_without_role(router):
    router.register(
        "ops", lambda argv, ctx: CommandResult(text="ok"),
        required_role="admin",
    )
    result = router.dispatch("/ops")
    assert result is not None
    assert result.succeeded is False


def test_role_required_allows_when_context_matches(router):
    router.register(
        "ops", lambda argv, ctx: CommandResult(text="ok"),
        required_role="admin",
    )
    result = router.dispatch("/ops", context={"user_role": "Admin"})
    assert result is not None
    assert result.succeeded is True


def test_unregister_drops_handler(router):
    router.register("ping", lambda argv, ctx: CommandResult(text="x"))
    assert router.unregister("ping") is True
    assert router.dispatch("/ping").succeeded is False


# === default handlers ====================================================

def _write_script(root: Path, name: str) -> Path:
    path = root / name
    path.write_text("[]", encoding="utf-8")
    return path


def test_cmd_scripts_lists_files(tmp_path):
    _write_script(tmp_path, "alpha.json")
    _write_script(tmp_path, "beta.json")
    result = cmd_scripts([], {"script_root": str(tmp_path)})
    assert "alpha.json" in result.text
    assert "beta.json" in result.text


def test_cmd_scripts_reports_empty(tmp_path):
    result = cmd_scripts([], {"script_root": str(tmp_path)})
    assert "no scripts" in result.text


def test_cmd_scripts_requires_root():
    with pytest.raises(ChatOpsError):
        cmd_scripts([], {})


def test_cmd_run_rejects_missing_arg(tmp_path):
    with pytest.raises(ChatOpsError):
        cmd_run([], {"script_root": str(tmp_path)})


def test_cmd_run_rejects_too_many_args(tmp_path):
    with pytest.raises(ChatOpsError):
        cmd_run(["a", "b"], {"script_root": str(tmp_path)})


def test_cmd_run_rejects_path_traversal(tmp_path):
    with pytest.raises(ChatOpsError):
        cmd_run(["../escape.json"], {"script_root": str(tmp_path)})


def test_cmd_run_rejects_missing_file(tmp_path):
    with pytest.raises(ChatOpsError):
        cmd_run(["nope.json"], {"script_root": str(tmp_path)})


def test_cmd_run_invokes_executor(tmp_path):
    script = _write_script(tmp_path, "do.json")
    with patch(
        "je_auto_control.utils.executor.action_executor.execute_files",
        return_value=[{"ok": True}],
    ) as mocked:
        result = cmd_run(["do.json"],
                          {"script_root": str(tmp_path)})
    mocked.assert_called_once_with([str(script)])
    assert "do.json" in result.text


def test_cmd_screenshot_invokes_screen_helper(tmp_path):
    target = tmp_path / "shot.png"
    with patch(
        "je_auto_control.wrapper.auto_control_screen.screenshot",
    ) as mocked:
        result = cmd_screenshot([str(target)], {})
    mocked.assert_called_once_with(file_path=str(target))
    assert result.artifact_path == str(target)


def test_cmd_status_renders_recent_runs():
    class _FakeRow:
        status = "succeeded"
        source_type = "scheduler"
        source_id = "job-1"
        started_at = "2026-01-01T00:00:00"
        duration_seconds = 1.25

    with patch(
        "je_auto_control.utils.run_history.history_store"
        ".default_history_store.list_runs",
        return_value=[_FakeRow()],
    ):
        result = cmd_status([], {})
    assert "scheduler:job-1" in result.text


def test_cmd_status_handles_empty_history():
    with patch(
        "je_auto_control.utils.run_history.history_store"
        ".default_history_store.list_runs",
        return_value=[],
    ):
        result = cmd_status([], {})
    assert "no recent runs" in result.text


# === Slack adapter =======================================================

def test_slack_bot_rejects_bad_token():
    with pytest.raises(SlackError):
        SlackBot(token="bad", channel_id="C1",
                  router=CommandRouter())


def test_slack_bot_rejects_blank_channel():
    with pytest.raises(SlackError):
        SlackBot(token="xoxb-abc", channel_id="",
                  router=CommandRouter())


def test_slack_bot_rejects_short_poll_interval():
    with pytest.raises(SlackError):
        SlackBot(token="xoxb-abc", channel_id="C1",
                  router=CommandRouter(), poll_interval_s=0.1)


def test_slack_bot_request_refuses_non_slack_url():
    bot = SlackBot(token="xoxb-abc", channel_id="C1",
                    router=CommandRouter())
    with pytest.raises(SlackError):
        bot._request("https://attacker.example/api", method="GET")


def test_slack_poll_once_dispatches_new_messages():
    router = CommandRouter()
    captured: list = []
    router.register(
        "ping", lambda argv, ctx: captured.append(ctx) or CommandResult(
            text="pong",
        ),
    )
    bot = SlackBot(token="xoxb-abc", channel_id="C1", router=router)

    def fake_get(method, params):
        if method == "auth.test":
            return {"ok": True, "user_id": "U_BOT"}
        return {
            "ok": True,
            "messages": [
                {"ts": "100.5", "user": "U2", "text": "/ping"},
            ],
        }

    posts: list = []

    def fake_post(method, payload):
        posts.append((method, payload))
        return {"ok": True}

    with patch.object(bot, "_api_get", side_effect=fake_get), \
         patch.object(bot, "_api_post", side_effect=fake_post):
        count = bot.poll_once()
    assert count == 1
    assert captured and captured[0]["slack_user"] == "U2"
    assert posts and posts[0][0] == "chat.postMessage"
    assert posts[0][1]["text"] == "pong"
    assert bot.last_seen_ts == "100.5"


def test_slack_poll_once_skips_bot_messages():
    router = CommandRouter()
    bot = SlackBot(token="xoxb-abc", channel_id="C1", router=router)

    def fake_get(method, params):
        return {
            "ok": True,
            "messages": [
                {"ts": "1", "subtype": "bot_message", "text": "/ping"},
            ],
        }

    with patch.object(bot, "_api_get", side_effect=fake_get), \
         patch.object(bot, "_api_post", return_value={"ok": True}):
        assert bot.poll_once() == 0


# === executor / MCP / façade ============================================

def test_executor_registers_chatops_dispatch():
    from je_auto_control.utils.executor.action_executor import executor
    assert "AC_chatops_dispatch" in executor.known_commands()


def test_executor_chatops_dispatch_round_trips(tmp_path):
    _write_script(tmp_path, "demo.json")
    from je_auto_control.utils.executor.action_executor import executor
    handler = executor.event_dict["AC_chatops_dispatch"]
    result = handler("/scripts", script_root=str(tmp_path))
    assert result["matched"] is True
    assert "demo.json" in result["text"]


def test_executor_chatops_dispatch_no_match():
    from je_auto_control.utils.executor.action_executor import executor
    handler = executor.event_dict["AC_chatops_dispatch"]
    assert handler("plain text", script_root=None) == {"matched": False}


def test_mcp_factory_registers_chatops_tool():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert "ac_chatops_dispatch" in names


def test_facade_exports_chatops_api():
    import je_auto_control as ac
    for name in ("CommandRouter", "SlackBot", "ChatOpsError",
                  "register_chatops_default_commands"):
        assert hasattr(ac, name)


def test_command_result_to_dict_round_trips():
    result = CommandResult(text="ok", succeeded=True,
                            metadata={"k": [1, 2, 3]})
    data = result.to_dict()
    assert json.dumps(data)  # JSON-safe
    assert data["text"] == "ok"
