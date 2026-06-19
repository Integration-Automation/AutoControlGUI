"""Headless tests for the ops batch: CycloneDX SBOM generation and
duration-aware suite sharding + shard-result merge. Pure stdlib; no Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.sbom import build_sbom, write_sbom
from je_auto_control.utils.test_shard import merge_results, shard_flows


# --- SBOM -----------------------------------------------------------------

def test_sbom_core_shape():
    sbom = build_sbom("je_auto_control")
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert isinstance(sbom["components"], list) and sbom["components"]
    comp = sbom["components"][0]
    assert {"type", "name", "version", "purl"} <= set(comp)
    assert comp["purl"].startswith("pkg:pypi/")


def test_sbom_extra_components_and_write(tmp_path):
    extra = [{"type": "file", "name": "login.json", "version": "1"}]
    sbom = build_sbom("je_auto_control", extra_components=extra)
    assert any(c["name"] == "login.json" for c in sbom["components"])
    path = write_sbom(str(tmp_path / "s.cdx.json"), "je_auto_control")
    assert json.loads(open(path, encoding="utf-8").read())["specVersion"] == \
        "1.6"


# --- suite sharding -------------------------------------------------------

def test_shard_balances_by_duration(tmp_path):
    from je_auto_control.utils.run_history import HistoryStore
    db = str(tmp_path / "h.sqlite")
    store = HistoryStore(db)
    # "slow" ~ long duration, three "fast" ~ short.
    durations = {"slow": 9.0, "f1": 1.0, "f2": 1.0, "f3": 1.0}
    for flow, secs in durations.items():
        rid = store.start_run("manual", "x", flow, started_at=1000.0)
        store.finish_run(rid, "ok", finished_at=1000.0 + secs)
    store.close()
    shards = shard_flows(list(durations), 2, history_path=db)
    assert len(shards) == 2
    # the heavy flow is alone; the three light flows share the other shard
    heavy = [s for s in shards if "slow" in s][0]
    assert heavy == ["slow"]
    other = [s for s in shards if s != heavy][0]
    assert sorted(other) == ["f1", "f2", "f3"]


def test_shard_unknown_flows_spread_evenly():
    shards = shard_flows(["a", "b", "c", "d"], 2)   # no history
    assert len(shards) == 2
    assert sorted(len(s) for s in shards) == [2, 2]


def test_merge_results_sums_and_concatenates():
    merged = merge_results([
        {"total": 3, "passed": 2, "failed": 1, "results": ["a", "b"]},
        {"total": 2, "passed": 2, "failed": 0, "results": ["c"]},
    ])
    assert merged["total"] == 5 and merged["passed"] == 4
    assert merged["failed"] == 1 and merged["shards"] == 2
    assert merged["results"] == ["a", "b", "c"]


# --- wiring ---------------------------------------------------------------

def test_executor_wiring(tmp_path):
    rec = ac.execute_action([["AC_generate_sbom", {
        "path": str(tmp_path / "e.cdx.json"), "root": "je_auto_control"}]])
    assert any("path" in str(v) for v in rec.values())
    sh = ac.execute_action([["AC_shard_suite", {
        "flows": ["a", "b", "c"], "shards": 2}]])
    assert any("shards" in str(v) for v in sh.values())
    known = ac.executor.known_commands()
    assert {"AC_generate_sbom", "AC_shard_suite", "AC_merge_results"} <= known


def test_mcp_and_builder_wiring():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_generate_sbom", "ac_shard_suite", "ac_merge_results"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_generate_sbom", "AC_shard_suite", "AC_merge_results"} <= cmds


def test_facade_exports():
    for attr in ("build_sbom", "write_sbom", "shard_flows", "merge_results"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
