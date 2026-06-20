"""Headless tests for multi-channel webhook notifications. The transport is
injected (or a module-default), so no network is used. Pure stdlib, no Qt."""
import je_auto_control as ac
from je_auto_control.utils.notify_channels import (
    WebhookChannel, notify_webhook, set_default_poster)


def _capturing_poster(status=200):
    sent = []

    def poster(url, payload):
        sent.append((url, payload))
        return status

    return sent, poster


def test_slack_payload_shape():
    sent, poster = _capturing_poster()
    notify_webhook("https://h/x", "hi", transport="slack", poster=poster)
    assert sent[0][1] == {"text": "hi"}


def test_discord_uses_content_key():
    sent, poster = _capturing_poster()
    notify_webhook("https://h/x", "hi", transport="discord", title="T",
                   poster=poster)
    assert "content" in sent[0][1]
    assert "text" not in sent[0][1]
    assert "T" in sent[0][1]["content"]


def test_teams_messagecard():
    sent, poster = _capturing_poster()
    notify_webhook("https://h/x", "hi", transport="teams", title="T",
                   poster=poster)
    card = sent[0][1]
    assert card["@type"] == "MessageCard"
    assert card["text"] == "hi" and card["title"] == "T"


def test_raw_payload():
    sent, poster = _capturing_poster()
    notify_webhook("https://h/x", "hi", title="T", poster=poster)
    assert sent[0][1] == {"text": "hi", "title": "T"}


def test_result_ok_by_status():
    _, ok_poster = _capturing_poster(204)
    _, bad_poster = _capturing_poster(500)
    assert notify_webhook("https://h/x", "hi", poster=ok_poster).ok is True
    assert notify_webhook("https://h/x", "hi", poster=bad_poster).ok is False


def test_channel_reuse():
    sent, poster = _capturing_poster()
    channel = WebhookChannel("https://h/x", transport="slack", poster=poster)
    channel.send("a")
    channel.send("b")
    assert [p["text"] for _, p in sent] == ["a", "b"]


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip_with_default_poster():
    sent, poster = _capturing_poster(200)
    set_default_poster(poster)
    try:
        rec = ac.execute_action([[
            "AC_notify_webhook",
            {"url": "https://h/x", "text": "done", "transport": "discord"},
        ]])
        out = next(v for v in rec.values() if isinstance(v, dict))
        assert out["ok"] is True and out["transport"] == "discord"
        assert sent and sent[0][1]["content"] == "done"
    finally:
        set_default_poster(None)        # leave global state clean


def test_wiring():
    assert "AC_notify_webhook" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_notify_webhook" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert "AC_notify_webhook" in cmds


def test_facade_exports():
    for attr in ("WebhookChannel", "WebhookResult", "notify_webhook",
                 "set_default_poster"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
