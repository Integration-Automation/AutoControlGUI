"""Headless tests for the tooling batch: synthetic data, MCP registry
manifest, and risk-based test selection. Pure stdlib; no Qt imports."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.test_data import generate_rows, write_dataset
from je_auto_control.utils.test_select import rank_flows, select_flows
from je_auto_control.utils.mcp_registry import (
    build_server_manifest, write_server_manifest)


# --- synthetic data -------------------------------------------------------

def test_generate_rows_is_deterministic_and_typed():
    schema = {"name": "name", "age": {"type": "int", "min": 18, "max": 65},
              "email": {"type": "email", "domain": "acme.test"}}
    a = generate_rows(schema, 5, seed=7)
    b = generate_rows(schema, 5, seed=7)
    assert a == b                       # same seed -> same rows
    assert len(a) == 5
    assert generate_rows(schema, 5, seed=8) != a
    row = a[0]
    assert 18 <= row["age"] <= 65
    assert row["email"].endswith("@acme.test")
    assert " " in row["name"]


def test_generate_rows_rejects_unknown_type():
    with pytest.raises(ValueError):
        generate_rows({"x": "not_a_type"}, 1)


def test_write_dataset_json_and_csv(tmp_path):
    rows = generate_rows({"id": "uuid", "n": "int"}, 3, seed=1)
    jpath = write_dataset(rows, str(tmp_path / "d.json"))
    assert json.loads(open(jpath, encoding="utf-8").read()) == rows
    cpath = write_dataset(rows, str(tmp_path / "d.csv"))
    text = open(cpath, encoding="utf-8").read()
    assert text.splitlines()[0] == "id,n"


# --- MCP registry manifest ------------------------------------------------

def test_build_server_manifest_core_fields():
    m = build_server_manifest()
    assert m["name"] and m["version"]
    assert m["packages"][0]["registryType"] == "pypi"
    assert m["repository"]["source"] == "github"
    assert "_meta" not in m


def test_manifest_include_tools_embeds_live_list(tmp_path):
    m = build_server_manifest(include_tools=True)
    meta = m["_meta"][m["name"]]
    assert meta["toolCount"] == len(meta["tools"]) > 0
    assert any(t.startswith("ac_") for t in meta["tools"])
    path = write_server_manifest(str(tmp_path / "server.json"))
    assert json.loads(open(path, encoding="utf-8").read())["name"] == m["name"]


# --- risk-based test selection -------------------------------------------

@pytest.fixture()
def history(tmp_path):
    from je_auto_control.utils.run_history import HistoryStore
    store = HistoryStore(str(tmp_path / "h.sqlite"))
    for status in ("ok", "ok", "ok"):
        rid = store.start_run("manual", "x", "flow_pass")
        store.finish_run(rid, status)
    rid = store.start_run("manual", "x", "flow_fail")
    store.finish_run(rid, "error")
    store.close()
    return str(tmp_path / "h.sqlite")


def test_rank_orders_by_risk(history):
    ranked = rank_flows(["flow_pass", "flow_fail", "flow_new"],
                        history_path=history)
    order = [r["flow"] for r in ranked]
    assert order[0] == "flow_new"          # untested == riskiest (0.8)
    assert order.index("flow_fail") < order.index("flow_pass")
    by = {r["flow"]: r for r in ranked}
    assert by["flow_new"]["runs"] == 0
    assert by["flow_fail"]["last_status"] == "error"


def test_rank_uses_shared_default_store(monkeypatch):
    # history_path=None must use the shared default_history_store *instance*
    # (not call it). Guards against the "not callable" regression.
    import je_auto_control.utils.run_history as rh
    from je_auto_control.utils.run_history import HistoryStore
    monkeypatch.setattr(rh, "default_history_store", HistoryStore(":memory:"))
    ranked = rank_flows(["never_run"])
    assert ranked[0]["flow"] == "never_run"
    assert ranked[0]["runs"] == 0


def test_select_top_k_and_threshold(history):
    flows = ["flow_pass", "flow_fail", "flow_new"]
    assert select_flows(flows, k=2, history_path=history) == \
        ["flow_new", "flow_fail"]
    assert select_flows(flows, threshold=0.75, history_path=history) == \
        ["flow_new"]


# --- wiring ---------------------------------------------------------------

def test_executor_wiring(tmp_path):
    rec = ac.execute_action(
        [["AC_generate_data", {"schema": {"n": "int"}, "count": 3, "seed": 1}]])
    assert any("'count': 3" in str(v) for v in rec.values())
    known = ac.executor.known_commands()
    assert {"AC_generate_data", "AC_mcp_manifest", "AC_rank_tests",
            "AC_select_tests"} <= known


def test_mcp_and_builder_wiring():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_generate_data", "ac_mcp_manifest", "ac_rank_tests",
            "ac_select_tests"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_generate_data", "AC_mcp_manifest", "AC_rank_tests",
            "AC_select_tests"} <= cmds


def test_facade_exports():
    for attr in ("generate_rows", "write_dataset", "rank_flows",
                 "select_flows", "build_server_manifest",
                 "write_server_manifest"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
