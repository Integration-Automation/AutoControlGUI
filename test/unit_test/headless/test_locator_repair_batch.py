"""Headless tests for self-healing locator write-back. Pure stdlib (JSON store),
no model/screen; no Qt imports."""
import je_auto_control as ac
from je_auto_control.utils.locator_repair import RepairStore, repair_from_heal


def test_high_confidence_auto_applies():
    store = RepairStore()
    sug = store.record("login", method="vlm", coordinates=[10, 20],
                       description="Login", confidence=0.95)
    assert sug.status == "applied"
    assert store.resolved("login") == {"method": "vlm",
                                       "coordinates": [10, 20],
                                       "description": "Login"}


def test_low_confidence_queues_pending():
    store = RepairStore()
    sug = store.record("save", method="image", coordinates=[5, 5],
                       confidence=0.5)
    assert sug.status == "pending"
    assert store.resolved("save") is None        # not usable until approved
    assert [p["key"] for p in store.pending()] == ["save"]


def test_approve_makes_resolvable():
    store = RepairStore()
    sug = store.record("save", method="image", coordinates=[5, 5],
                       confidence=0.5)
    assert store.approve(sug.id) is True
    assert store.resolved("save")["coordinates"] == [5, 5]
    assert store.pending() == []


def test_reject_keeps_unresolved():
    store = RepairStore()
    sug = store.record("x", method="image", confidence=0.1)
    assert store.reject(sug.id) is True
    assert store.resolved("x") is None
    assert store.approve(sug.id) is False         # already decided


def test_latest_wins():
    store = RepairStore()
    store.record("btn", method="image", coordinates=[1, 1], confidence=1.0)
    store.record("btn", method="vlm", coordinates=[2, 2], confidence=1.0)
    assert store.resolved("btn")["coordinates"] == [2, 2]


def test_repair_from_heal_object_and_dict():
    store = RepairStore()

    class _Heal:
        method = "vlm"
        coordinates = [7, 8]
        description = "OK"

    s1 = repair_from_heal(_Heal(), "a", store=store, confidence=1.0)
    s2 = repair_from_heal({"method": "image", "coordinates": [9, 9]}, "b",
                          store=store, confidence=1.0)
    assert s1.coordinates == [7, 8] and s2.method == "image"


def test_persists_across_instances(tmp_path):
    db = str(tmp_path / "repairs.json")
    sug = RepairStore(db).record("k", method="vlm", coordinates=[1, 2],
                                 confidence=0.4)
    assert RepairStore(db).approve(sug.id) is True
    assert RepairStore(db).resolved("k")["coordinates"] == [1, 2]


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip(tmp_path):
    db = str(tmp_path / "r.json")
    ac.execute_action([["AC_repair_record",
                        {"key": "login", "method": "vlm",
                         "coordinates": [3, 4], "confidence": 0.95, "db": db}]])
    rec = ac.execute_action([["AC_repair_resolved",
                              {"key": "login", "db": db}]])
    loc = next(v for v in rec.values() if isinstance(v, dict))["locator"]
    assert loc["coordinates"] == [3, 4]


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_repair_record", "AC_repair_resolved", "AC_repair_pending",
            "AC_repair_approve"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_repair_record", "ac_repair_resolved", "ac_repair_pending",
            "ac_repair_approve"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_repair_record", "AC_repair_resolved", "AC_repair_pending",
            "AC_repair_approve"} <= cmds


def test_facade_exports():
    for attr in ("RepairStore", "RepairSuggestion", "repair_from_heal"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
