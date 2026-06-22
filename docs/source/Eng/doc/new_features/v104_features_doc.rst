Time-Windowed Deduplication
===========================

``work_queue`` dedups only ``new`` / ``in_progress`` references — once an item
completes, the same reference enqueues again, and redelivered webhooks are
reprocessed. This adds the missing "seen this id in the last N seconds → drop
it" inbox that converts at-least-once delivery to exactly-once-in-window.

Pure standard library; imports no ``PySide6``. The clock is injectable, so TTL
eviction is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import DedupWindow

    inbox = DedupWindow(ttl_s=3600)
    if inbox.check_and_mark(event_id):
        process(event)           # first time within the window
    else:
        skip(event)              # duplicate / redelivery

``check_and_mark`` atomically returns ``True`` the first time an id is seen
within the window (and marks it) or ``False`` for a duplicate. ``seen`` / ``mark``
are the separate query/record halves, ``purge_expired`` drops stale entries, and
``size`` reports the live count. Entries older than ``ttl_s`` are evicted on each
operation, so the window stays bounded.

Executor command
----------------

``AC_dedup_check`` check-and-marks a ``message_id`` in a named window (TTL
``ttl_s``) and returns ``{first_seen, size}``. It uses a named-instance registry
and is exposed as the MCP tool ``ac_dedup_check`` and as a Script Builder
command under **Flow**.
