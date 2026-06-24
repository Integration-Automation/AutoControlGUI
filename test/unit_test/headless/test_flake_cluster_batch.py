"""Headless tests for co-failure flake clustering (Jaccard over failing runs)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.flake_cluster import cofailure_pairs, failure_clusters


def _runs():
    # a&b always fail together; c&d always together; e fails alone
    return [
        ["a", "b"],
        ["a", "b"],
        ["c", "d"],
        ["a", "b", "c", "d"],
        ["e"],
        ["c", "d"],
    ]


def test_clusters_group_cofailing_tests():
    clusters = failure_clusters(_runs(), threshold=0.6)
    grouped = sorted(tuple(c["tests"]) for c in clusters)
    assert grouped == [("a", "b"), ("c", "d")]
    assert all(c["cohesion"] == pytest.approx(1.0) for c in clusters)
    assert all(c["size"] == 2 for c in clusters)


def test_singleton_excluded_by_min_size():
    # 'e' never co-fails, so it is not in any cluster of size >= 2
    tests_in_clusters = {t for c in failure_clusters(_runs()) for t in c["tests"]}
    assert "e" not in tests_in_clusters


def test_min_size_includes_singletons_when_one():
    clusters = failure_clusters([["e"]], threshold=0.5, min_size=1)
    assert clusters == [{"tests": ["e"], "size": 1, "cohesion": 1.0}]


def test_high_threshold_keeps_only_perfect_cofailure():
    # a&b co-fail perfectly (jaccard 1.0); a&c only sometimes
    clusters = failure_clusters(_runs(), threshold=0.95)
    assert sorted(tuple(c["tests"]) for c in clusters) == [("a", "b"), ("c", "d")]


def test_cofailure_pairs_scores_and_sorted():
    pairs = cofailure_pairs(_runs(), threshold=0.6)
    assert {tuple(p["tests"]) for p in pairs} == {("a", "b"), ("c", "d")}
    assert pairs[0]["jaccard"] == pytest.approx(1.0)
    assert pairs[0]["co_failures"] == 3


def test_empty_and_no_cofailure():
    assert failure_clusters([]) == []
    assert failure_clusters([["x"], ["y"], ["z"]]) == []   # nobody co-fails


# --- wiring ---------------------------------------------------------------

def test_executor_paths():
    import json
    from je_auto_control.utils.executor.action_executor import (
        _cofailure_pairs, _failure_clusters)
    runs_json = json.dumps(_runs())
    clusters = _failure_clusters(runs_json, threshold=0.6)
    assert clusters["count"] == 2
    pairs = _cofailure_pairs(runs_json, threshold=0.6)
    assert pairs["count"] == 2


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_failure_clusters", "AC_cofailure_pairs"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_failure_clusters", "ac_cofailure_pairs"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_failure_clusters", "AC_cofailure_pairs"} <= specs


def test_facade_exports():
    for name in ("cofailure_pairs", "failure_clusters"):
        assert hasattr(ac, name) and name in ac.__all__
