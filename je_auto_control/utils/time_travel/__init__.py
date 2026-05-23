"""Phase 9.4: time-travel debugging for recorded sessions.

A session recording is two streams indexed by timestamp:

  * **screen frames** — JPEG payloads from
    :class:`utils.remote_desktop.jpeg_recorder.JpegSequenceRecorder`,
    optionally encrypted via Phase 6.2's
    :class:`EncryptedJpegSequenceRecorder`.
  * **action log** — a sequence of :class:`ActionEvent` rows
    describing the AC_* commands the executor ran while the
    recording was open.

This module joins the two streams. Given a wall-clock or relative
step index, :class:`TimelinePlayer` returns the matching frame and
the list of actions that happened around it — so an operator can
scrub backwards to see "what did the screen look like *just before*
the click that broke?".

The headless player is what the GUI scrubber binds to. Tests cover
the join logic, lookup performance, and the manifest schema.
"""
from je_auto_control.utils.time_travel.player import (
    ActionEvent, FrameRef, TimelinePlayer, TimelineSnapshot,
    load_action_log, save_action_log,
)

__all__ = [
    "ActionEvent", "FrameRef", "TimelinePlayer", "TimelineSnapshot",
    "load_action_log", "save_action_log",
]
