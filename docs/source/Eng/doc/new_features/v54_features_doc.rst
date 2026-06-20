Self-Healing Locator Write-Back
===============================

The self-healing locator finds an element at a new place at runtime and logs the
heal — but the *corrected* location was then thrown away, so the next run healed
from scratch. ``RepairStore`` closes that loop: it records the corrected locator
(coordinates / VLM description / method) from a heal, **auto-applies** it when
confidence is high enough, otherwise queues it as a *pending suggestion* for
review. A later run reads the learned fix via :meth:`RepairStore.resolved`.

JSON-backed (via the shared ``json_store`` helper); pure standard library;
confidence and threshold are explicit, so behavior is deterministic and fully
unit-testable. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import RepairStore, repair_from_heal

    store = RepairStore("repairs.json")
    # high-confidence heal -> applied immediately:
    store.record("login_btn", method="vlm", coordinates=[120, 64],
                 description="Login", confidence=0.95)
    store.resolved("login_btn")        # -> {method, coordinates, description}

    # low-confidence heal -> queued for review:
    s = store.record("save_btn", method="image", coordinates=[5, 5],
                     confidence=0.5)
    store.pending()                    # -> [the save_btn suggestion]
    store.approve(s.id)                # now store.resolved("save_btn") works

    # straight from a HealEvent (object or dict):
    repair_from_heal(heal_event, "login_btn", store=store, confidence=0.9)

``record`` auto-applies when ``confidence >= auto_threshold`` (default 0.9), else
files a ``pending`` suggestion; ``approve`` / ``reject`` decide queued ones;
``resolved(key)`` returns the latest applied/approved corrected locator (or
``None``) — the durable fix a future run reuses instead of re-healing.

Executor commands
-----------------

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_repair_record``             Persist a corrected locator (auto-apply or queue).
``AC_repair_resolved``           Get the learned corrected locator for a key.
``AC_repair_pending``            List suggestions awaiting review.
``AC_repair_approve``            Approve a pending suggestion.
================================ ===================================================

The same operations are exposed as MCP tools (``ac_repair_*``) and as Script
Builder commands under **Tools**.
