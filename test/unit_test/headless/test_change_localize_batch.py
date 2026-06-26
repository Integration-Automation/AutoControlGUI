"""Headless tests for change_localize (pure ranking + cv2 localization)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.change_localize import localize_changes, rank_changes


# --- pure rank_changes ----------------------------------------------------

def test_rank_changes_marks_and_sorts():
    scored = [{"box": [0, 0, 10, 10], "score": 0.02},
              {"box": [20, 20, 10, 10], "score": 0.5},
              {"box": [40, 40, 10, 10], "score": 0.2}]
    ranked = rank_changes(scored, threshold=0.1)
    # sorted most-changed first
    assert [entry["score"] for entry in ranked] == pytest.approx([0.5, 0.2,
                                                                  0.02])
    assert [entry["changed"] for entry in ranked] == [True, True, False]


def test_rank_changes_accepts_tuples():
    ranked = rank_changes([([0, 0, 5, 5], 0.3), ([1, 1, 5, 5], 0.05)],
                          threshold=0.1)
    assert ranked[0]["changed"] is True
    assert ranked[1]["changed"] is False


def test_rank_changes_empty():
    assert rank_changes([]) == []


def test_rank_changes_threshold_boundary():
    # a score exactly at the threshold counts as changed (>=)
    ranked = rank_changes([{"box": [0, 0, 1, 1], "score": 0.1}], threshold=0.1)
    assert ranked[0]["changed"] is True


# --- cv2 localize_changes (per-function importorskip) ---------------------

def test_localize_changes_attributes_to_the_right_box():
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    reference = np.zeros((100, 100), dtype="uint8")
    current = reference.copy()
    current[40:60, 40:60] = 255            # change inside this box only
    boxes = [[40, 40, 20, 20], [0, 0, 20, 20]]
    ranked = localize_changes(reference, boxes, current=current,
                              threshold=0.05)
    # the changed box ranks first and is flagged; the untouched one is not
    assert ranked[0]["box"] == [40, 40, 20, 20]
    assert ranked[0]["changed"] is True
    untouched = [r for r in ranked if r["box"] == [0, 0, 20, 20]][0]
    assert untouched["changed"] is False


# --- wiring (cv2-free) ----------------------------------------------------

def test_executor_pure_rank_path():
    from je_auto_control.utils.executor.action_executor import _rank_changes
    out = _rank_changes('[{"box": [0,0,4,4], "score": 0.4}]', 0.1)
    assert out["changes"][0]["changed"] is True


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_rank_changes", "AC_localize_changes"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_rank_changes", "ac_localize_changes"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_rank_changes", "AC_localize_changes"} <= specs


def test_facade_exports():
    for name in ("localize_changes", "rank_changes"):
        assert hasattr(ac, name) and name in ac.__all__
