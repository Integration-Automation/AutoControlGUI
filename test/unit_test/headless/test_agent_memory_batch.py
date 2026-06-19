"""Headless tests for the agent-memory batch: episodic memory store and
deterministic-run harness. Pure stdlib; no Qt imports."""
import random
import time

import pytest

import je_auto_control as ac
from je_auto_control.utils.agent_memory import AgentMemory
from je_auto_control.utils.deterministic import (
    DeterministicRun, seed_everything)


# --- agent memory ---------------------------------------------------------

@pytest.fixture()
def mem(tmp_path):
    return AgentMemory(str(tmp_path / "mem.db"))


def test_remember_get_forget(mem):
    eid = mem.remember("log in to portal",
                       steps=[["AC_click_mouse", {}]], outcome="success",
                       tags=["auth"])
    episode = mem.get(eid)
    assert episode.goal == "log in to portal"
    assert episode.steps == [["AC_click_mouse", {}]]
    assert episode.tags == ["auth"]
    assert mem.forget(eid) is True
    assert mem.forget(eid) is False
    assert mem.get(eid) is None


def test_remember_requires_goal(mem):
    with pytest.raises(ValueError):
        mem.remember("   ")


def test_recall_ranks_by_relevance(mem):
    mem.remember("log in to the billing portal", outcome="ok", tags=["auth"])
    mem.remember("export the monthly sales report", tags=["report"])
    mem.remember("download invoice pdf", tags=["billing"])
    hits = mem.recall("portal login auth", limit=5)
    assert hits[0].goal == "log in to the billing portal"
    assert hits[0].score > 0
    assert mem.recall("nonexistent-term-xyz") == []


def test_recent_and_stats(mem):
    for i in range(3):
        mem.remember(f"goal {i}")
    assert [e.goal for e in mem.recent(limit=2)] == ["goal 2", "goal 1"]
    assert mem.stats() == {"episodes": 3}


# --- deterministic run ----------------------------------------------------

def test_seed_makes_random_reproducible():
    with DeterministicRun(seed=5):
        first = [random.random() for _ in range(3)]
    with DeterministicRun(seed=5):
        second = [random.random() for _ in range(3)]
    assert first == second


def test_freeze_time_and_restore():
    real_before = time.time()
    with DeterministicRun(seed=1, freeze_time=1000.0) as run:
        assert time.time() == 1000.0
        assert time.time_ns() == 1000_000_000_000
        assert run.manifest() == {"seed": 1, "freeze_time": 1000.0}
    assert time.time() >= real_before          # clock restored


def test_seed_everything_returns_seed():
    assert seed_everything(7) == 7


# --- wiring ---------------------------------------------------------------

def test_executor_wiring(tmp_path):
    db = str(tmp_path / "e.db")
    ac.execute_action([["AC_memory_remember", {
        "db": db, "goal": "do a thing", "tags": ["x"]}]])
    rec = ac.execute_action([["AC_memory_recall", {
        "db": db, "query": "thing"}]])
    assert any("do a thing" in str(v) for v in rec.values())
    seeded = ac.execute_action([["AC_seed_everything", {"seed": 9}]])
    assert any("'seed': 9" in str(v) for v in seeded.values())
    known = ac.executor.known_commands()
    assert {"AC_memory_remember", "AC_memory_recall", "AC_memory_recent",
            "AC_memory_forget", "AC_memory_stats", "AC_seed_everything"} <= \
        known


def test_mcp_and_builder_wiring():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_memory_remember", "ac_memory_recall", "ac_memory_recent",
            "ac_memory_forget", "ac_memory_stats", "ac_seed_everything"} <= \
        names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_memory_remember", "AC_memory_recall", "AC_memory_recent",
            "AC_memory_forget", "AC_memory_stats", "AC_seed_everything"} <= \
        cmds


def test_facade_exports():
    for attr in ("AgentMemory", "Episode", "DeterministicRun",
                 "seed_everything"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
