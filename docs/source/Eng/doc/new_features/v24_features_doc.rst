==================================================
New Features (2026-06-19) — Timed Input Macros
==================================================

Replay recorded input with timing fidelity, and author press-hold-release
combos with a small declarative DSL. Pure standard library; full stack.
Both dispatch through an injectable sink and sleep, so they unit-test
deterministically with a fake clock and a recording sink.

.. contents::
   :local:
   :depth: 2


Timed timeline replay
====================

::

    from je_auto_control import replay_timeline

    events = [{"op": "move", "x": 10, "y": 10, "delta_ms": 0},
              {"op": "click", "x": 10, "y": 10, "delta_ms": 120},
              {"op": "key", "key": "a", "delta_ms": 80}]
    replay_timeline(events, speed=2.0)   # plays twice as fast; gaps clampable

Each event's ``delta_ms`` gap is honored, divided by ``speed`` (and clamped
to ``[min_gap, max_gap]``). Event ``op`` is one of ``move`` / ``click`` /
``scroll`` / ``press`` / ``release`` / ``key``. Exposed as
``AC_replay_timeline`` / ``ac_replay_timeline``.


Input-sequence DSL
=================

::

    from je_auto_control import run_sequence

    run_sequence([
        {"op": "press", "key": "ctrl"},
        {"op": "repeat", "times": 3, "steps": [{"op": "key", "key": "a"}]},
        {"op": "wait", "ms": 50},
        {"op": "release", "key": "ctrl"},
    ])

A declarative mini-language for press-hold-release chords and repeated
input: action ops (``press`` / ``release`` / ``key`` / ``click`` / ``move``
/ ``scroll``) plus control ops ``{op: wait, ms}`` and
``{op: repeat, times, steps:[...]}``. Returns the flattened executed log.
Exposed as ``AC_input_sequence`` / ``ac_input_sequence``.
