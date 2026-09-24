"""Data-format defects from the 2026-09-24 audit.

A scraped string starting with "=" became a live formula in exported
workbooks; malformed JSON Patch operations raised KeyError / AttributeError
and "~2" was a valid escape; unsupported JSONPath selectors and filter values
silently matched nothing, and filters tested an object instead of its members;
ICU plural offsets, quoted apostrophes, empty branches and stray braces were
mishandled; XML empty elements could not round-trip; integer -> number and
object / boolean enums confused the schema diff; ``ignore`` could not cover a
subtree; short values were "partially" masked in full view; unhashable unique
values crashed; misplaced grouping separators parsed.
"""
import pytest

from je_auto_control.utils.data_quality.data_quality import mask_rows, validate_rows
from je_auto_control.utils.json_contract.json_contract import match_json
from je_auto_control.utils.json_patch.json_patch import PatchError, apply_patch, resolve_pointer
from je_auto_control.utils.jsonpath.jsonpath import json_query
from je_auto_control.utils.message_format.message_format import format_message
from je_auto_control.utils.office import office
from je_auto_control.utils.schema_compat.schema_compat import diff_schemas
from je_auto_control.utils.xml.change_xml_structure.change_xml_structure import (
    dict_to_elements_tree,
)


class _Cell:
    def __init__(self, value):
        self.value = value
        # What openpyxl does: a string starting with "=" is a formula.
        self.data_type = "f" if isinstance(value, str) and value.startswith("=") else "s"


class _Sheet:
    def __init__(self):
        self.rows = []

    def append(self, values):
        self.rows.append([_Cell(value) for value in values])

    @property
    def max_row(self):
        return len(self.rows)

    def __getitem__(self, row):
        return self.rows[row - 1]


def test_exported_formula_looking_strings_stay_text():
    sheet = _Sheet()
    office._append_as_data(sheet, ["=HYPERLINK(\"http://x\")", "plain"])
    assert [cell.data_type for cell in sheet.rows[0]] == ["s", "s"]


def test_a_real_workbook_keeps_formula_text_and_every_column(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = office.write_workbook(str(tmp_path / "w.xlsx"),
                                 [{"a": "=1+1"}, {"a": "x", "b": "late key"}])
    sheet = openpyxl.load_workbook(path).active
    assert [cell.value for cell in sheet[1]] == ["a", "b"]
    assert sheet["A2"].data_type == "s" and sheet["A2"].value == "=1+1"
    assert sheet["B3"].value == "late key"


@pytest.mark.parametrize("op", [
    {"op": "test", "path": "/a"}, {"op": "add", "value": 1}, {"op": "move", "path": "/b"},
    "x", {"op": "add", "path": 5, "value": 1},
])
def test_malformed_patch_operations_are_patch_errors(op):
    with pytest.raises(PatchError):
        apply_patch({"a": 1}, [op])


def test_invalid_pointer_escapes_are_refused():
    with pytest.raises(PatchError):
        resolve_pointer({"a~2": 1}, "/a~2")
    assert resolve_pointer({"a~b": 1, "c/d": 2}, "/a~0b") == 1


@pytest.mark.parametrize("path", ["$[0:2]", "$[0,1]", "$[]", "$[?(@.a==1 && @.b==2)]",
                                  "$[?(@.a==1_000)]", "$[?(@.a==nan)]"])
def test_unsupported_jsonpath_syntax_raises(path):
    with pytest.raises(ValueError):
        json_query([{"a": 1}], path)


def test_a_filter_on_an_object_selects_among_its_members():
    data = {"x": {"a": 1}, "y": {"a": 2}}
    assert json_query(data, "$[?(@.a==1)]") == [{"a": 1}]
    assert json_query([{"a": 1}, {"a": 2}], "$[?(@.a==2)]") == [{"a": 2}]


def test_icu_plural_offset_selects_by_the_offset_value():
    pattern = ("{n, plural, offset:1 =0 {nobody} =1 {just you} "
               "one {you and # other} other {you and # others}}")
    assert format_message(pattern, {"n": 2}) == "you and 1 other"
    assert format_message(pattern, {"n": 3}) == "you and 2 others"


def test_icu_quoting_and_empty_branches():
    assert format_message("'{a''b}' tail") == "{a'b} tail"
    assert format_message("{n, plural, one {} other {items}}", {"n": 1}) == ""
    assert format_message("{g, select, male {} other {x}}", {"g": "male"}) == ""


def test_icu_stray_brace_and_non_numeric_plural_are_value_errors():
    with pytest.raises(ValueError):
        format_message("a } b")
    with pytest.raises(ValueError):
        format_message("{n, plural, other {x}}", {"n": None})


def test_xml_empty_elements_and_numbers_round_trip():
    text = dict_to_elements_tree({"a": {"b": None, "c": "1", "d": 2}})
    assert "<b" in text and "<d>2</d>" in text


def _prop_schema(prop):
    return {"type": "object", "properties": {"x": prop}}


def test_integer_to_number_is_a_widening():
    changes = diff_schemas(_prop_schema({"type": "integer"}), _prop_schema({"type": "number"}))
    assert [change.kind for change in changes] == ["type_widened"]


def test_enums_of_objects_and_booleans_compare_as_json():
    changes = diff_schemas(_prop_schema({"enum": [[1]]}), _prop_schema({"enum": [[1]]}))
    assert changes == []
    changes = diff_schemas(_prop_schema({"enum": [True]}), _prop_schema({"enum": [1]}))
    assert {change.kind for change in changes} == {"enum_value_removed", "enum_value_added"}


def test_ignore_covers_a_whole_subtree():
    assert match_json({"ts": {"s": 1}}, {"ts": {"s": 2}}, ignore=["$.ts"]).ok
    assert not match_json({"tsx": 1}, {"tsx": 2}, ignore=["$.ts"]).ok


def test_short_values_are_masked_completely():
    assert mask_rows([{"pin": "1234"}], {"pin": "partial"}) == [{"pin": "****"}]
    assert mask_rows([{"card": "4111111111111111"}], {"card": "partial"}) == [
        {"card": "************1111"}]


def test_unique_accepts_unhashable_values():
    report = validate_rows([{"t": [1]}, {"t": [1]}, {"t": [2]}], {"t": {"unique": True}})
    assert [error["row"] for error in report["errors"]] == [1]


def test_misplaced_grouping_and_fractions_are_refused():
    pytest.importorskip("babel")
    from je_auto_control.utils.locale_parse.locale_parse import parse_decimal, parse_number
    with pytest.raises(ValueError):
        parse_decimal("1,5", "en_US")
    assert parse_decimal("1,234.5", "en_US") == 1234.5
    with pytest.raises(ValueError):
        parse_number("1.5", "en_US")
    assert parse_number("1,234", "en_US") == 1234
