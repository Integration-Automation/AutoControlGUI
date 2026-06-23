"""Headless tests for heading vs body classification + outline (pure stdlib)."""
import je_auto_control as ac
from je_auto_control.utils.heading_segment import classify_lines, outline


def _line(y, text, h=20, x=0, w=200):
    return {"x": x, "y": y, "width": w, "height": h, "text": text}


def _doc():
    # one big title (h=40), some body (h=20), a smaller heading (h=30)
    return [_line(0, "Title", h=40), _line(50, "body one"),
            _line(75, "body two"), _line(110, "Subsection", h=30),
            _line(145, "more body")]


def test_classify_marks_headings_and_levels():
    by_text = {c["text"]: c for c in classify_lines(_doc(), heading_ratio=1.2)}
    assert by_text["Title"]["role"] == "heading"
    assert by_text["Subsection"]["role"] == "heading"
    assert by_text["body one"]["role"] == "body"
    # tallest heading is level 1, the next distinct height is level 2
    assert by_text["Title"]["level"] == 1
    assert by_text["Subsection"]["level"] == 2


def test_body_only_has_no_headings():
    lines = [_line(0, "a"), _line(25, "b"), _line(50, "c")]
    assert all(c["role"] == "body" for c in classify_lines(lines))


def test_outline_lists_headings_in_order():
    result = outline(_doc(), heading_ratio=1.2)
    assert [h["text"] for h in result] == ["Title", "Subsection"]
    assert [h["level"] for h in result] == [1, 2]


def test_empty():
    assert classify_lines([]) == []
    assert outline([]) == []


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_classify_lines", "AC_outline"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_classify_lines", "ac_outline"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_classify_lines", "AC_outline"} <= specs


def test_facade_exports():
    for name in ("classify_lines", "outline"):
        assert hasattr(ac, name) and name in ac.__all__
