Transactional Outbox
====================

``events.cloud_events`` posts immediately and synchronously — a crash between
"did the work" and "sent the event" loses it, and a network blip drops it (no
durability, no retry, no replay). The transactional-outbox pattern persists each
event first and drains it later with at-least-once delivery and a dead-letter
cap, so events survive sink outages.

Pure standard library (``json``); imports no ``PySide6``. The delivery ``sink``
is injected and the store is in-memory with JSON persistence, so draining is
fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import Outbox

    box = Outbox()
    box.enqueue({"type": "order.created", "id": 7})    # buffered, pending
    box.enqueue({"type": "order.paid", "id": 7})

    result = box.drain(post_to_webhook, max_batch=100, max_attempts=5)
    # {"sent": 2, "failed": 0, "remaining": 0}

    box.pending()        # entries still awaiting delivery
    box.dead_letters()   # entries that exhausted their attempts

``enqueue`` appends an event as pending and returns its id. ``drain`` delivers
up to ``max_batch`` pending entries through the injected ``sink``; a sink
exception leaves the entry pending for retry until ``max_attempts``, after which
it is dead-lettered (recorded with its error). Delivery is at-least-once: a sink
that succeeds but is interrupted before the entry is marked sent will be retried.
``save`` / ``load`` persist the whole buffer as JSON so events outlive the
process.

Executor commands
-----------------

``AC_outbox_enqueue`` returns ``{id, pending}``; ``AC_outbox_pending`` returns
``{pending}``. Both use a named-instance registry and are exposed as MCP tools
(``ac_outbox_enqueue`` / ``ac_outbox_pending``) and as Script Builder commands
under **Flow**. Draining requires a callable sink, so it stays a headless / API
operation.
