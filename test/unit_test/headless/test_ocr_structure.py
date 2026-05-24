"""Tests for the structured OCR layer (rows / tables / fields)."""
from unittest.mock import patch

from je_auto_control.utils.ocr.ocr_engine import TextMatch
from je_auto_control.utils.ocr.structure import (
    StructuredOCR, cluster_matches, read_structure,
)


def _match(text, x, y, w=40, h=14, conf=92.0) -> TextMatch:
    return TextMatch(text=text, x=x, y=y, width=w,
                      height=h, confidence=conf)


# === empty input ==========================================================

def test_cluster_matches_empty_returns_empty_structured():
    result = cluster_matches([])
    assert isinstance(result, StructuredOCR)
    assert result.matches == ()
    assert result.rows == ()
    assert result.tables == ()
    assert result.fields == ()


# === row clustering =======================================================

def test_cluster_matches_groups_by_y_with_default_tolerance():
    matches = [
        _match("alpha", x=0, y=20, w=40, h=14),
        _match("beta", x=60, y=22, w=40, h=14),
        _match("gamma", x=0, y=60, w=40, h=14),
    ]
    result = cluster_matches(matches)
    assert len(result.rows) == 2
    assert [c.text for c in result.rows[0].cells] == ["alpha", "beta"]
    assert [c.text for c in result.rows[1].cells] == ["gamma"]


def test_cluster_matches_sorts_cells_by_x_within_row():
    matches = [
        _match("right", x=120, y=20),
        _match("left", x=0, y=20),
    ]
    result = cluster_matches(matches)
    assert [c.text for c in result.rows[0].cells] == ["left", "right"]


def test_cluster_matches_respects_explicit_row_tolerance():
    matches = [
        _match("a", x=0, y=10, w=40, h=14),
        _match("b", x=60, y=24, w=40, h=14),
    ]
    # With default tolerance (~7px) these are two rows; widen it.
    result = cluster_matches(matches, row_tolerance_px=20.0)
    assert len(result.rows) == 1


# === table detection ======================================================

def _table_rows(start_y: int, count: int) -> list:
    matches = []
    for row_index in range(count):
        y = start_y + row_index * 30
        matches.append(_match("name", x=0, y=y))
        matches.append(_match("value", x=80, y=y))
        matches.append(_match("status", x=180, y=y))
    return matches


def test_three_rows_with_aligned_columns_detect_as_table():
    matches = _table_rows(start_y=20, count=3)
    result = cluster_matches(matches)
    assert len(result.tables) == 1
    table = result.tables[0]
    assert table.column_count == 3
    assert len(table.rows) == 3


def test_table_needs_min_rows_to_be_detected():
    matches = _table_rows(start_y=20, count=1)
    result = cluster_matches(matches, min_table_rows=2)
    assert result.tables == ()


def test_table_needs_min_columns_to_be_detected():
    matches = [
        _match("only", x=0, y=20),
        _match("one", x=0, y=50),
    ]
    result = cluster_matches(matches, min_table_columns=2)
    assert result.tables == ()


def test_column_drift_beyond_tolerance_splits_table():
    rows_a = _table_rows(start_y=20, count=2)
    # Misaligned third row — should NOT join the table
    rows_b = [
        _match("first", x=300, y=80),
        _match("second", x=400, y=80),
        _match("third", x=500, y=80),
    ]
    result = cluster_matches(rows_a + rows_b, column_tolerance_px=5.0)
    assert len(result.tables) <= 1
    if result.tables:
        assert len(result.tables[0].rows) == 2


# === field detection ======================================================

def test_field_detected_when_label_ends_with_colon():
    matches = [
        _match("Username:", x=0, y=20),
        _match("jeff", x=80, y=20),
    ]
    result = cluster_matches(matches)
    assert len(result.fields) == 1
    field = result.fields[0]
    assert field.label == "Username"
    assert field.value == "jeff"


def test_field_value_can_live_on_next_row():
    matches = [
        _match("Username:", x=0, y=20),
        _match("alice", x=0, y=50),
    ]
    result = cluster_matches(matches)
    assert len(result.fields) == 1
    assert result.fields[0].value == "alice"


def test_no_field_when_no_value_available():
    matches = [_match("Username:", x=0, y=20)]
    result = cluster_matches(matches)
    assert result.fields == ()


def test_fields_independent_of_table_detection():
    matches = [
        _match("Email:", x=0, y=20),
        _match("u@example.com", x=80, y=20),
        _match("Role:", x=0, y=50),
        _match("admin", x=80, y=50),
    ]
    result = cluster_matches(matches)
    labels = sorted(f.label for f in result.fields)
    values = sorted(f.value for f in result.fields)
    assert labels == ["Email", "Role"]
    assert values == ["admin", "u@example.com"]


# === serialisation ========================================================

def test_to_dict_is_json_safe():
    import json
    matches = [
        _match("Username:", x=0, y=20),
        _match("alice", x=80, y=20),
    ]
    result = cluster_matches(matches)
    encoded = json.dumps(result.to_dict())
    decoded = json.loads(encoded)
    assert decoded["fields"][0]["label"] == "Username"
    assert decoded["matches"][0]["x"] == 0


# === read_structure dispatch =============================================

def test_read_structure_calls_read_text_in_region():
    with patch(
        "je_auto_control.utils.ocr.ocr_engine.read_text_in_region",
        return_value=[_match("Username:", x=0, y=10),
                      _match("alice", x=80, y=10)],
    ) as mocked:
        result = read_structure(region=[0, 0, 200, 100])
    mocked.assert_called_once()
    assert isinstance(result, StructuredOCR)
    assert len(result.fields) == 1


# === executor / mcp / facade =============================================

def test_executor_registers_ocr_read_structure():
    from je_auto_control.utils.executor.action_executor import executor
    assert "AC_ocr_read_structure" in executor.known_commands()


def test_mcp_factory_registers_ocr_structure_tool():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert "ac_ocr_read_structure" in names


def test_facade_exports_ocr_structure_api():
    import je_auto_control as ac
    for name in ("OCRField", "OCRRow", "OCRTable", "StructuredOCR",
                  "ocr_cluster_matches", "ocr_read_structure"):
        assert hasattr(ac, name)
