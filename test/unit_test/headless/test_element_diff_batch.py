"""Headless tests for geometry-aware element diff / stable IDs. No Qt."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.element_diff import assign_stable_ids, match_elements


def _b(x, y, w, h, **extra):
    return dict(x=x, y=y, width=w, height=h, **extra)


def test_match_pairs_added_removed():
    before = [_b(10, 10, 40, 20, name="Save"), _b(100, 10, 40, 20, name="Delete")]
    after = [_b(12, 11, 40, 20, name="Save"), _b(300, 300, 50, 25, name="New")]
    result = match_elements(before, after)
    assert len(result["matched"]) == 1
    assert result["matched"][0]["before"]["name"] == "Save"
    assert [a["name"] for a in result["added"]] == ["New"]
    assert [r["name"] for r in result["removed"]] == ["Delete"]


def test_match_iou_recorded():
    pair = match_elements([_b(0, 0, 10, 10)], [_b(0, 0, 10, 10)])["matched"][0]
    assert pair["iou"] == pytest.approx(1.0)


def test_no_match_below_threshold():
    result = match_elements([_b(0, 0, 10, 10)], [_b(50, 0, 10, 10)],
                            iou_threshold=0.5)
    assert result["matched"] == [] and len(result["added"]) == 1
    assert len(result["removed"]) == 1


def test_assign_ids_fresh_without_prior():
    ids = [e["id"] for e in assign_stable_ids([_b(0, 0, 5, 5), _b(9, 9, 5, 5)])]
    assert ids == [0, 1]


def test_assign_ids_carry_from_prior():
    prior = assign_stable_ids([_b(10, 10, 40, 20, name="Save"),
                               _b(100, 10, 40, 20, name="Delete")])
    nxt = assign_stable_ids([_b(12, 11, 40, 20, name="Save"),
                             _b(300, 300, 50, 25, name="New")], prior=prior)
    by_name = {e["name"]: e["id"] for e in nxt}
    assert by_name["Save"] == 0          # carried despite the 2px move
    assert by_name["New"] == 2           # fresh id beyond the prior max (1)


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_match_elements", "AC_assign_stable_ids"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_match_elements", "ac_assign_stable_ids"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_match_elements", "AC_assign_stable_ids"} <= specs


def test_facade_exports():
    for attr in ("match_elements", "assign_stable_ids"):
        assert hasattr(ac, attr) and attr in ac.__all__
