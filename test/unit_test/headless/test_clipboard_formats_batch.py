"""Headless tests for clipboard-format classification + diff (pure; Win32 enum skipped)."""
import je_auto_control as ac
from je_auto_control.utils.clipboard_formats import (
    classify_format, classify_formats, diff_formats,
)


def test_classify_standard_ids():
    assert classify_format(13) == "text"      # CF_UNICODETEXT
    assert classify_format(1) == "text"       # CF_TEXT
    assert classify_format(8) == "image"      # CF_DIB
    assert classify_format(15) == "files"     # CF_HDROP
    assert classify_format(99999) == "other"


def test_classify_named_takes_priority():
    # registered ids are dynamic (>= 0xC000); the name decides the category
    assert classify_format(49161, "Csv") == "csv"
    assert classify_format(49383, "HTML Format") == "html"
    assert classify_format(50000, "Rich Text Format") == "rtf"
    assert classify_format(49500, "PNG") == "image"


def test_classify_formats_summary():
    summary = classify_formats([13, {"id": 15, "name": ""},
                                {"id": 49383, "name": "HTML Format"}])
    assert summary["categories"] == ["files", "html", "text"]
    assert summary["has_text"] is True
    assert summary["has_files"] is True
    assert summary["has_image"] is False
    assert {"id": 15, "name": "", "category": "files"} in summary["formats"]


def test_diff_formats_added_removed():
    before = [13, 1]
    after = [13, 15, {"id": 49383, "name": "HTML Format"}]
    diff = diff_formats(before, after)
    assert diff["changed"] is True
    added_cats = {f["category"] for f in diff["added"]}
    removed_cats = {f["category"] for f in diff["removed"]}
    assert added_cats == {"files", "html"}
    assert removed_cats == {"text"}            # CF_TEXT(1) dropped; CF_UNICODETEXT kept


def test_diff_formats_no_change():
    diff = diff_formats([13, 15], [15, 13])
    assert diff == {"added": [], "removed": [], "changed": False}


def test_tuple_descriptor_accepted():
    assert classify_formats([(49161, "Csv")])["categories"] == ["csv"]


# --- wiring (Win32 enumeration not executed in CI) -------------------------

def test_executor_pure_paths():
    from je_auto_control.utils.executor.action_executor import (
        _classify_formats, _diff_formats)
    assert _classify_formats("[13, 15]")["has_files"] is True
    assert _diff_formats("[13]", "[13, 15]")["changed"] is True


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_clipboard_formats", "AC_classify_formats",
            "AC_diff_formats"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_clipboard_formats", "ac_classify_formats",
            "ac_diff_formats"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_clipboard_formats", "AC_classify_formats",
            "AC_diff_formats"} <= specs


def test_facade_exports():
    for name in ("classify_format", "classify_formats", "diff_formats",
                 "list_clipboard_formats", "clipboard_formats"):
        assert hasattr(ac, name) and name in ac.__all__
