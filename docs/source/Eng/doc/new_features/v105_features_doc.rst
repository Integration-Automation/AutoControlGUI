Per-Stream Sequence-Gap Detection
=================================

Nothing tracked per-stream monotonic sequence numbers to detect missing,
out-of-order, or duplicate messages. ``dedup_window`` says "seen this id
before"; this complements it by classifying each sequence number and tracking
the outstanding gaps and high-water mark per stream.

Pure standard library; imports no ``PySide6``. State is in-memory and fully
injectable, so detection is deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import SequenceTracker

    tracker = SequenceTracker()
    tracker.observe("orders", 1)      # {"status": "ok", ...}
    tracker.observe("orders", 4)      # {"status": "gap", "missing": [2, 3]}
    tracker.observe("orders", 3)      # {"status": "reorder", "missing": [2]}
    tracker.gaps("orders")            # [2]
    tracker.high_water("orders")      # 4

``observe`` returns ``{status, seq, missing}`` where status is ``ok`` (next in
order or the first seen), ``duplicate`` (already seen), ``gap`` (numbers were
skipped — they are recorded as missing), or ``reorder`` (a late earlier number,
which fills a gap when applicable). ``gaps`` lists the outstanding missing
numbers and ``high_water`` is the highest seen. Streams are tracked
independently by ``stream_id``.

Executor command
----------------

``AC_sequence_observe`` observes a ``seq`` on a ``stream_id`` in a named tracker
and returns the classification. It uses a named-instance registry and is exposed
as the MCP tool ``ac_sequence_observe`` and as a Script Builder command under
**Flow**.
