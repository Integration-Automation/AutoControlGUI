==================================================
New Features (2026-06-19) — Memory & Determinism
==================================================

Two pure-standard-library tools surfaced by the agent / QA research round,
wired through the full stack (facade, ``AC_*`` executor commands, MCP
tools, Script Builder): a persistent **agent episodic memory** store and a
**deterministic run** harness.

.. contents::
   :local:
   :depth: 2


Agent episodic memory
====================

An agent that re-derives "how do I log in to this app" every run wastes
tokens and repeats mistakes. :class:`AgentMemory` records each episode —
the goal, the trajectory (steps / tool-calls), and the outcome — to a
SQLite file, and recalls the most relevant past episodes by keyword so they
can be injected into the planner's context::

    from je_auto_control import AgentMemory

    mem = AgentMemory("agent.memory.db")
    mem.remember("log in to the billing portal",
                 steps=recorded_actions, outcome="success", tags=["auth"])

    for episode in mem.recall("portal login", limit=3):
        ...   # feed episode.goal / episode.steps back to the planner

Recall scores each episode by term frequency over its goal + tags +
outcome (a dependency-free BM25 stand-in); a vector tier can be added later
without changing the API. Commands: ``AC_memory_remember`` /
``AC_memory_recall`` / ``AC_memory_recent`` / ``AC_memory_forget`` /
``AC_memory_stats`` (and the matching ``ac_memory_*`` MCP tools).


Deterministic run
================

Time and randomness are two of the top causes of flaky automation.
:class:`DeterministicRun` pins both for a ``with`` block and records the
choices so a run can be reproduced exactly::

    from je_auto_control import DeterministicRun

    with DeterministicRun(seed=42, freeze_time=1_750_000_000.0) as run:
        ...                      # random.* reproducible; time.time() frozen
    manifest = run.manifest()    # {"seed": 42, "freeze_time": 1750000000.0}

Scope (pure standard library — no ``freezegun`` dependency): it seeds the
global :mod:`random` generator (and numpy if present) and restores its
state on exit, and patches ``time.time`` / ``time.time_ns`` to a fixed
instant. ``time.monotonic`` is deliberately left alone so duration
measurements and timeouts keep working.

``seed_everything(seed)`` is the standalone seeding helper, also exposed as
``AC_seed_everything`` / ``ac_seed_everything`` for run-wide reproducibility
from a flow.
