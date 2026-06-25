Verify a Field After Typing
===========================

``field_entry`` types into a control and *hopes* it landed. A slow IME, a focus
steal, an input mask or an auto-format can silently mangle or drop characters,
and nothing reads the field back to notice. This is distinct from
``action_effect`` (did *anything* change near the target?) and
``postcondition.text_present`` (does the text appear *anywhere* on screen?) —
neither confirms *this* field now equals *this* value. ``verify_field`` closes
the read-back gap.

* :func:`compare_field_value` — pure: compare an expected and actual value under
  a match ``mode`` — ``exact`` / ``trim`` / ``ci`` (case-insensitive) /
  ``normalized`` (Unicode NFKC + case-fold + whitespace) / ``contains``.
* :func:`verify_field_value` — read the field through an injectable ``reader``
  and compare.
* :func:`fill_and_verify` — type through an injectable ``filler``, read back, and
  retry (optionally clearing first) until it matches or attempts run out.

In the executor the reader is the native accessibility value, but every
comparison and retry decision is pure and testable without a real control.
Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        compare_field_value, verify_field_value, fill_and_verify,
    )

    compare_field_value("café", "café", mode="normalized")["match"]  # True

    # Read a control back and assert it took the value
    ok = verify_field_value("invoice.pdf",
                            reader=lambda: read_control_value())["match"]

    # Type, read back, and retry up to 3 times (clearing before each retry)
    fill_and_verify("2026-06-26", filler=type_into_field,
                    reader=read_control_value, attempts=3, clear=select_all_del)

``fill_and_verify`` returns the final :func:`compare_field_value` result plus an
``attempts`` count, so a flow can branch on a persistent mismatch instead of
typing blind. ``filler`` / ``reader`` / ``clear`` are injectable, so the retry
logic is fully unit-tested without a real field.

Executor commands
-----------------

``AC_compare_field_value`` (``expected`` / ``actual`` / ``mode`` → ``{match,
mode, expected, actual}``, pure) and ``AC_verify_field_value`` (``expected`` +
``name`` / ``role`` / ``app_name`` / ``automation_id`` / ``mode`` → the match
result, reading the control's value through the accessibility backend). They are
the matching read-only ``ac_*`` MCP tools and Script Builder commands under
**Flow**. :func:`fill_and_verify` (which wraps a typing callable) is the
Python-API surface.
