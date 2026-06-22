"""Headless tests for semantic screen state: snapshot/diff and describe.
Pure stdlib; diffs/describe run on supplied elements (no live desktop)."""
import je_auto_control as ac
from je_auto_control.utils.screen_state import (
    describe_screen, diff_snapshots, snapshot)


def test_snapshot_normalizes():
    snap = snapshot([{"role": "button", "name": "OK", "bbox": [0, 0, 10, 10]}])
    assert snap == [{"role": "button", "name": "OK", "bbox": [0, 0, 10, 10]}]


def test_diff_reports_appeared_vanished_moved():
    before = [{"role": "button", "name": "OK", "bbox": [0, 0, 10, 10]},
              {"role": "edit", "name": "user", "bbox": [0, 20, 50, 10]}]
    after = [{"role": "button", "name": "OK", "bbox": [5, 5, 10, 10]},
             {"role": "window", "name": "Save", "bbox": [0, 0, 200, 100]}]
    diff = diff_snapshots(before, after)
    assert [a["name"] for a in diff["added"]] == ["Save"]
    assert [r["name"] for r in diff["removed"]] == ["user"]
    assert [m["name"] for m in diff["moved"]] == ["OK"]
    assert diff["changed_count"] == 3
    assert any("appeared: window Save" in s for s in diff["summary"])


def test_diff_no_change():
    snap = [{"role": "button", "name": "OK", "bbox": [0, 0, 10, 10]}]
    diff = diff_snapshots(snap, snap)
    assert diff["changed_count"] == 0 and diff["summary"] == []


def test_describe_groups_and_lists_controls():
    elements = [
        {"role": "button", "name": "Save", "bbox": [0, 0, 10, 10]},
        {"role": "button", "name": "Cancel", "bbox": [0, 0, 10, 10]},
        {"role": "window", "name": "Dlg", "bbox": [0, 0, 10, 10]},
    ]
    out = describe_screen(elements=elements, app_name="MyApp")
    assert out["app"] == "MyApp" and out["element_count"] == 3
    assert out["by_role"]["button"] == 2
    assert set(out["controls"]) == {"Save", "Cancel"}     # window not a control


# --- wiring ---------------------------------------------------------------

def test_executor_wiring():
    rec = ac.execute_action([["AC_screen_diff", {
        "before": [], "after": [{"role": "x", "name": "y", "bbox": []}]}]])
    assert any("appeared" in str(v) for v in rec.values())
    known = ac.executor.known_commands()
    assert {"AC_screen_snapshot", "AC_screen_diff", "AC_screen_changed",
            "AC_describe_screen"} <= known


def test_mcp_and_builder_wiring():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_screen_snapshot", "ac_screen_diff", "ac_screen_changed",
            "ac_describe_screen"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_screen_snapshot", "AC_screen_diff", "AC_screen_changed",
            "AC_describe_screen"} <= cmds


def test_facade_exports():
    for attr in ("snapshot", "diff_snapshots", "screen_changed",
                 "snapshot_screen", "describe_screen"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
