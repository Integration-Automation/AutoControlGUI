"""Headless tests for unified-diff apply + three-way merge. Pure stdlib."""
import je_auto_control as ac
from je_auto_control.utils.text_diff import (
    MergeResult, PatchApplyError, apply_unified, three_way_merge, unified_diff)

import pytest

A = "line1\nline2\nline3\n"
B = "line1\nCHANGED\nline3\nline4\n"


def test_unified_diff_format():
    diff = unified_diff(A, B)
    assert "@@" in diff
    assert "-line2" in diff and "+CHANGED" in diff and "+line4" in diff


def test_apply_unified_round_trip():
    assert apply_unified(A, unified_diff(A, B)) == B


def test_apply_unified_context_mismatch():
    with pytest.raises(PatchApplyError):
        apply_unified("totally\ndifferent\ncontent\n", unified_diff(A, B))


def test_apply_unified_no_op():
    assert apply_unified(A, unified_diff(A, A)) == A


BASE = "a\nb\nc\nd\ne\n"


def test_three_way_clean_non_overlapping():
    result = three_way_merge(BASE, "A\nb\nc\nd\ne\n", "a\nb\nc\nd\nE\n")
    assert isinstance(result, MergeResult)
    assert result.clean is True
    assert result.text == "A\nb\nc\nd\nE\n"


def test_three_way_one_side_unchanged():
    assert three_way_merge(BASE, BASE, "a\nb\nC\nd\ne\n").text == "a\nb\nC\nd\ne\n"
    assert three_way_merge(BASE, "A\nb\nc\nd\ne\n", BASE).text == "A\nb\nc\nd\ne\n"


def test_three_way_identical_changes():
    same = "A\nb\nc\nd\ne\n"
    result = three_way_merge(BASE, same, same)
    assert result.clean is True and result.text == same


def test_three_way_conflict():
    result = three_way_merge(BASE, "X\nb\nc\nd\ne\n", "Y\nb\nc\nd\ne\n")
    assert result.clean is False
    assert result.conflicts == 1
    assert "<<<<<<<" in result.text and ">>>>>>>" in result.text


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    enc = ac.execute_action([["AC_unified_diff", {"a": A, "b": B}]])
    diff = next(v for v in enc.values() if isinstance(v, dict))["diff"]
    dec = ac.execute_action([["AC_apply_unified", {"text": A, "diff": diff}]])
    assert next(v for v in dec.values() if isinstance(v, dict))["result"] == B

    merged = ac.execute_action([[
        "AC_three_way_merge",
        {"base": BASE, "ours": "A\nb\nc\nd\ne\n", "theirs": "a\nb\nc\nd\nE\n"},
    ]])
    payload = next(v for v in merged.values() if isinstance(v, dict))
    assert payload["clean"] is True


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_unified_diff", "AC_apply_unified", "AC_three_way_merge"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_unified_diff", "ac_apply_unified", "ac_three_way_merge"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_unified_diff", "AC_apply_unified", "AC_three_way_merge"} <= cmds


def test_facade_exports():
    for attr in ("unified_diff", "apply_unified", "three_way_merge",
                 "MergeResult", "PatchApplyError"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
