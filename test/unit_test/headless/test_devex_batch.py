"""Headless tests for the devex batch: CI annotations + clipboard history.
Pure stdlib; no Qt imports, no real clipboard required."""
import io

import je_auto_control as ac
from je_auto_control.utils.ci_annotations import (
    emit_annotations, format_annotation)
from je_auto_control.utils.clipboard_history import ClipboardHistory


# --- CI annotations -------------------------------------------------------

def test_format_annotation_github_command():
    line = format_annotation({"level": "error", "message": "boom",
                              "file": "a.py", "line": 12, "title": "Fail"})
    assert line == "::error file=a.py,line=12,title=Fail::boom"


def test_format_annotation_escapes_and_defaults_level():
    line = format_annotation({"message": "a, b\nc", "file": "x,y.py"})
    assert line.startswith("::error file=x%2Cy.py::")
    assert "%0A" in line and line.count("::") >= 2     # newline escaped


def test_emit_annotations_writes_and_returns():
    buf = io.StringIO()
    lines = emit_annotations(
        [{"level": "warning", "message": "w"},
         {"level": "notice", "message": "n"}], stream=buf)
    assert lines == ["::warning::w", "::notice::n"]
    assert buf.getvalue() == "::warning::w\n::notice::n\n"


# --- clipboard history ----------------------------------------------------

def test_history_dedup_move_to_front_and_cap():
    hist = ClipboardHistory(capacity=3)
    assert hist.add("a") is True
    assert hist.add("a") is False           # unchanged top -> skipped
    hist.add("b")
    hist.add("c")
    hist.add("a")                            # re-add moves to front
    assert hist.snapshot() == ["a", "c", "b"]
    hist.add("d")                            # cap=3 evicts oldest ("b")
    assert hist.snapshot() == ["d", "a", "c"]
    assert hist.add("") is False


def test_history_get_search_clear():
    hist = ClipboardHistory()
    for text in ("alpha", "beta", "alphabet"):
        hist.add(text)
    assert hist.get(0) == "alphabet"
    assert hist.get(99) is None
    assert set(hist.search("alpha")) == {"alpha", "alphabet"}
    hist.clear()
    assert hist.snapshot() == []


def test_capture_once_uses_clipboard(monkeypatch):
    import je_auto_control.utils.clipboard.clipboard as clip
    monkeypatch.setattr(clip, "get_clipboard", lambda: "copied")
    hist = ClipboardHistory()
    assert hist.capture_once() is True
    assert hist.snapshot() == ["copied"]


# --- wiring ---------------------------------------------------------------

def test_executor_wiring():
    rec = ac.execute_action([["AC_ci_annotations", {
        "annotations": [{"level": "error", "message": "x"}]}]])
    assert any("::error::x" in str(v) for v in rec.values())
    known = ac.executor.known_commands()
    assert {"AC_ci_annotations", "AC_clip_history_capture",
            "AC_clip_history_list", "AC_clip_history_search",
            "AC_clip_history_start", "AC_clip_history_stop"} <= known


def test_mcp_and_builder_wiring():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_ci_annotations", "ac_clip_history_capture",
            "ac_clip_history_list", "ac_clip_history_search"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_ci_annotations", "AC_clip_history_capture",
            "AC_clip_history_search"} <= cmds


def test_facade_exports():
    for attr in ("emit_annotations", "format_annotation", "ClipboardHistory",
                 "default_clipboard_history"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
