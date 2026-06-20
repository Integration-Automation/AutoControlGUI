Task / Process Mining (Automation-Candidate Discovery)
======================================================

Enterprise RPA suites *discover* what to automate by mining recorded desktop
actions for frequent, repeatable sub-sequences. AutoControl records rich action
logs but never analysed them; ``mine_action_log`` turns a log into a ranked list
of automation candidates — it counts repeated command n-grams, builds a
directly-follows graph, and scores candidates by how often **and** how long each
repeated run is.

It operates on the project's action-list shape (each step is a ``["AC_name",
{...}]`` pair or a ``{"command": "AC_name", ...}`` mapping). Pure standard
library (``collections``); imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import mine_action_log, directly_follows

    report = mine_action_log(recorded_actions, min_len=2, max_len=5, min_count=3)
    report.total_actions
    for cand in report.candidates[:5]:        # best first
        print(cand.pattern.actions, cand.pattern.count, cand.score)

    directly_follows(recorded_actions)        # {(a, b): edge_count} flow graph

``find_repeated_sequences`` returns the raw n-gram :class:`SequencePattern` list;
``rank_automation_candidates`` scores them (``count × length`` — more and longer
repeats rank higher). A candidate that recurs often and spans several steps is a
strong "extract this into a reusable skill" signal.

Executor command
----------------

``AC_mine_actions`` takes ``actions`` (a list, or a JSON-string list from the
visual builder) plus ``min_len`` / ``max_len`` / ``min_count`` and returns
``{total_actions, patterns, candidates}``. The same operation is exposed as the
MCP tool ``ac_mine_actions`` and as a Script Builder command under **Report**.
