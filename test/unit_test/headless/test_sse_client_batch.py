"""Headless tests for the SSE (text/event-stream) client parser. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.sse_client import (
    SSEEvent, SSEParser, parse_event_stream,
)


def test_basic_event():
    events = parse_event_stream("data: hello\n\n")
    assert events == [SSEEvent(event="message", data="hello")]


def test_named_event_multiline_data_and_id():
    stream = "event: update\ndata: line1\ndata: line2\nid: 42\n\n"
    [event] = parse_event_stream(stream)
    assert event.event == "update"
    assert event.data == "line1\nline2"      # data lines joined with \n
    assert event.id == "42"


def test_comment_and_leading_space_rule():
    stream = ": this is a comment\ndata:  two-spaces\n\n"
    [event] = parse_event_stream(stream)
    assert event.data == " two-spaces"        # only ONE leading space removed


def test_retry_and_id_persist_across_events():
    stream = "retry: 3000\nid: a\ndata: one\n\ndata: two\n\n"
    first, second = parse_event_stream(stream)
    assert first.retry == 3000 and first.id == "a"
    assert second.retry == 3000 and second.id == "a"   # both persist


def test_blank_data_does_not_dispatch():
    # event type with no data line → no event
    assert parse_event_stream("event: ping\n\n") == []


def test_incremental_feed_across_chunks():
    parser = SSEParser()
    assert parser.feed("data: par") == []     # partial line buffered
    assert parser.feed("tial\n\n") == [SSEEvent(data="partial")]


def test_crlf_line_endings():
    [event] = parse_event_stream("data: win\r\n\r\n")
    assert event.data == "win"


def test_trailing_event_without_blank_line_flushed():
    [event] = parse_event_stream("data: last")   # no final blank line
    assert event.data == "last"


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_parse_sse", {"text": "event: tick\ndata: 1\n\n"}]])
    events = next(v for v in rec.values() if isinstance(v, dict))["events"]
    assert events == [{"event": "tick", "data": "1", "id": None, "retry": None}]


def test_wiring():
    assert "AC_parse_sse" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_parse_sse" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_parse_sse" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("SSEEvent", "SSEParser", "parse_event_stream"):
        assert hasattr(ac, attr) and attr in ac.__all__
