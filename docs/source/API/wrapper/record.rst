==========
Record API
==========

Functions for recording and replaying mouse/keyboard events.

----

record
======

.. function:: record()

   Starts recording all keyboard and mouse events in the background.
   Recording continues until :func:`stop_record` is called.

   :returns: None

----

stop_record
===========

.. function:: stop_record()

   Stops the current recording session and returns the captured events.

   :returns: List of recorded actions in executor-compatible format.
   :rtype: list

   The returned list can be passed directly to ``execute_action()`` for playback,
   or saved to a JSON file for later use.
