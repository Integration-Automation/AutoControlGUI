"""Headless tests for the CloudEvents emitter. The transport is injected, so
no network is used. Pure stdlib, no Qt imports."""
import je_auto_control as ac
from je_auto_control.utils.events import (
    EventEmitter, post_cloudevent, to_cloudevent)


def test_envelope_has_required_fields():
    event = to_cloudevent("com.example.run.finished", "/runs/42",
                          {"ok": True}, subject="run-42")
    assert event["specversion"] == "1.0"
    assert event["type"] == "com.example.run.finished"
    assert event["source"] == "/runs/42"
    assert event["subject"] == "run-42"
    assert event["data"] == {"ok": True}
    assert event["id"] and event["time"]
    assert event["datacontenttype"] == "application/json"


def test_ids_are_unique():
    a = to_cloudevent("t", "s", None)
    b = to_cloudevent("t", "s", None)
    assert a["id"] != b["id"]


def test_explicit_id_and_time_preserved():
    event = to_cloudevent("t", "s", None, event_id="fixed", time="2026-06-20T00:00:00Z")
    assert event["id"] == "fixed" and event["time"] == "2026-06-20T00:00:00Z"


def test_emitter_uses_default_sink():
    emitter = EventEmitter(source="je_auto_control")
    event = emitter.emit("run.started", {"flow": "x"})
    assert emitter.events == [event]
    assert event["source"] == "je_auto_control"


def test_emitter_uses_injected_sink():
    captured = []
    emitter = EventEmitter(sink=captured.append, source="svc")
    emitter.emit("a", 1)
    emitter.emit("b", 2)
    assert [e["type"] for e in captured] == ["a", "b"]


def test_post_cloudevent_uses_injected_poster():
    seen = {}

    def poster(url, event):
        seen["url"] = url
        seen["event"] = event
        return 202

    status = post_cloudevent("https://hooks.test/ce",
                             to_cloudevent("t", "s", {"k": 1}), poster=poster)
    assert status == 202
    assert seen["url"] == "https://hooks.test/ce"
    assert seen["event"]["data"] == {"k": 1}


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_emit_event",
        {"event_type": "run.finished", "data": {"run_id": "42"},
         "source": "/ci"},
    ]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["event"]["type"] == "run.finished"
    assert out["event"]["data"] == {"run_id": "42"}
    assert "status" not in out          # no url -> not posted


def test_wiring():
    assert "AC_emit_event" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_emit_event" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert "AC_emit_event" in cmds


def test_facade_exports():
    for attr in ("EventEmitter", "to_cloudevent", "post_cloudevent"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
