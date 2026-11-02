"""GUI map rows must measure their actual module lists and inline source counts."""
import pytest

from headless import test_doc_line_counts as measure


_HEADER = "| 分頁 | 模組 | 行數 | 職責 |"


def _document(row):
    return "### 5.5 GUI `gui/`\n\n" + _HEADER + "\n| --- | --- | ---: | --- |\n" + row + "\n"


def test_composite_gui_row_is_measured_from_every_source():
    row = "| run_history | `run_history_tab.py` + `run_history_timeline.py` | 1 | history |"
    expected = sum(measure._lines(measure.PACKAGE / "gui" / name)
                   for name in ("run_history_tab.py", "run_history_timeline.py"))
    result = measure.rewrite(_document(row))
    assert f"| {expected:,} | history |" in result


def test_gui_package_caption_and_total_use_the_same_tree():
    row = "| script_builder | `script_builder/` | 1 | `command_schema.py`（1 行 `AC_*` 參數綱要） |"
    folder = measure.PACKAGE / "gui" / "script_builder"
    result = measure.rewrite(_document(row))
    assert f"| {measure._measure(folder)[1]:,} |" in result
    assert f"`command_schema.py`（{measure._lines(folder / 'command_schema.py'):,} 行" in result


def test_unknown_gui_source_cannot_silently_escape_measurement():
    with pytest.raises(ValueError, match="no_such_gui_file"):
        measure.rewrite(_document("| missing | `no_such_gui_file.py` | 1 | missing |"))


def test_unresolved_rows_reports_gui_sources(tmp_path, monkeypatch):
    document = tmp_path / "map.md"
    document.write_text(_document("| missing | `no_such_gui_file.py` | 1 | missing |"), encoding="utf-8")
    monkeypatch.setattr(measure, "DOC", document)
    assert any("no_such_gui_file.py" in item for item in measure.unresolved_rows())
