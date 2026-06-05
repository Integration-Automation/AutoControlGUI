=====================
Recording & Playback
=====================

AutoControl can record mouse and keyboard events and replay them using the executor.

Record and Replay
=================

.. code-block:: python

   from time import sleep
   from je_auto_control import record, stop_record, execute_action

   # Start recording all mouse and keyboard events
   record()

   sleep(5)  # Record for 5 seconds

   # Stop and get the recorded action list
   actions = stop_record()
   print(actions)

   # Replay the recorded actions
   execute_action(actions)

.. note::

   Action recording is **not available on macOS**. See :doc:`/getting_started/installation` for platform support details.

How It Works
============

1. ``record()`` starts a background listener that captures all mouse and keyboard events.
2. ``stop_record()`` stops the listener and returns a list of actions in the executor-compatible format.
3. ``execute_action(actions)`` replays the captured actions through the built-in executor.

The recorded actions are in the same JSON format used by the :doc:`/Eng/doc/keyword_and_executor/keyword_and_executor_doc`, so you can save them to a file and replay later.

Editing a recording
===================

A raw recording captures one event per cursor sample, so it is large and
noisy. The :mod:`recording_edit.editor` helpers clean it up. They are
**non-destructive** — each returns a new list and leaves the input
untouched.

.. code-block:: python

   from je_auto_control import (
       dedupe_moves, merge_sleeps, trim_actions, adjust_delays,
       scale_coordinates,
   )

   actions = dedupe_moves(actions)          # collapse mouse-move runs to the final position
   actions = merge_sleeps(actions)          # sum consecutive AC_sleep delays into one
   actions = trim_actions(actions, 2, -1)   # drop the head/tail
   actions = adjust_delays(actions, 0.5)    # replay at 2x speed
   actions = scale_coordinates(actions, 1.5, 1.5)  # replay on a larger screen

``dedupe_moves`` keeps only the last move of each contiguous run (any
non-move action ends the run), typically shrinking a recording by an
order of magnitude without changing replay behaviour; pass
``move_commands=[...]`` to treat other commands as moves. ``merge_sleeps``
collapses each run of consecutive ``AC_sleep`` actions into a single
sleep summing their durations.

The remaining helpers — ``insert_action``, ``remove_action``,
``filter_actions`` — round out the toolkit. ``dedupe_moves``,
``merge_sleeps``, ``trim_actions``, ``adjust_delays`` and
``scale_coordinates`` are also exposed over MCP as ``ac_dedupe_moves`` /
``ac_merge_sleeps`` / ``ac_trim_actions`` / ``ac_adjust_delays`` /
``ac_scale_coordinates``.
