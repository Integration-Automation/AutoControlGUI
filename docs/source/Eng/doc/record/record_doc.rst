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
