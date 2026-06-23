"""Headless tests for paragraph / list grouping of OCR lines (pure stdlib)."""
import je_auto_control as ac
from je_auto_control.utils.text_blocks import detect_lists, group_paragraphs


def _line(y, text, x=0, w=200, h=20):
    return {"x": x, "y": y, "width": w, "height": h, "text": text}


def test_group_paragraphs_splits_on_large_gap():
    # two tight lines, a big gap, then two more tight lines → 2 paragraphs
    lines = [_line(0, "a1"), _line(25, "a2"),
             _line(120, "b1"), _line(145, "b2")]
    paras = group_paragraphs(lines, line_gap_factor=1.6)
    assert len(paras) == 2
    assert paras[0]["text"] == "a1 a2" and paras[1]["text"] == "b1 b2"
    assert paras[0]["n_lines"] == 2


def test_group_paragraphs_single_block():
    lines = [_line(0, "x"), _line(25, "y"), _line(50, "z")]
    paras = group_paragraphs(lines)
    assert len(paras) == 1 and paras[0]["text"] == "x y z"


def test_detect_lists_bullets_and_ordinals():
    lines = [_line(0, "• first"), _line(30, "2) second"),
             _line(60, "a. third"), _line(90, "not a list item")]
    items = detect_lists(lines)
    assert [i["text"] for i in items] == ["first", "second", "third"]
    assert items[0]["marker"] == "•" and items[1]["marker"] == "2)"


def test_detect_lists_indent_recorded():
    items = detect_lists([_line(0, "- top", x=10), _line(30, "- nested", x=40)])
    assert items[0]["indent"] == 10 and items[1]["indent"] == 40


def test_empty():
    assert group_paragraphs([]) == []
    assert detect_lists([]) == []


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_group_paragraphs", "AC_detect_lists"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_group_paragraphs", "ac_detect_lists"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_group_paragraphs", "AC_detect_lists"} <= specs


def test_facade_exports():
    for name in ("group_paragraphs", "detect_lists"):
        assert hasattr(ac, name) and name in ac.__all__
