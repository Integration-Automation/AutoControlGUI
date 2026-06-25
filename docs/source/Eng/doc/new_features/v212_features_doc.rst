Ensure a Control Is in the Desired State (Idempotent)
=====================================================

Automation that *acts unconditionally* — "click the checkbox", "type the value"
— double-toggles a box that was already checked, or re-enters a field that was
already correct, and can't be safely re-run. The robust shape is
read-compare-act-verify: look at the current state, do nothing if it already
matches, otherwise apply the change and confirm it took. ``ensure_state`` is
that primitive.

* :func:`ensure_state` — generic: read via ``reader``, and if it doesn't equal
  ``desired`` apply ``setter`` and re-read, up to ``attempts`` times.
* :func:`ensure_toggle` — the boolean specialization for a stateless flip: read
  ``is_on`` and call ``toggle`` only while it differs from ``desired``.

A control already in the desired state is left untouched (``changed=False``), so
the call is idempotent and safe to re-run. This is distinct from
:mod:`idempotency` (a request-key replay cache) — ``ensure_state`` converges
*device state*, not call results. The reader / setter / toggle seams are
injectable, so the logic is fully testable without a real control. Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import ensure_state, ensure_toggle

    # Idempotently make a setting "on" — no write if it already is
    ensure_state("on", reader=read_combo, setter=write_combo)
    # -> {'ok': True, 'changed': False, 'value': 'on', 'attempts': 0}

    # Flip a checkbox to checked only if it isn't already
    ensure_toggle(True, is_on=is_checked, toggle=click_checkbox)

Both return ``{ok, changed, value, attempts}``: ``changed`` tells you whether an
action was actually performed (useful for "did I have to fix this?" reporting),
and ``ok`` whether the desired state was reached within ``attempts``. Pass a
custom ``equals`` to :func:`ensure_state` for case-insensitive or normalized
comparisons.

Executor commands
-----------------

``AC_ensure_field_value`` (``desired`` + ``name`` / ``role`` / ``app_name`` /
``automation_id`` / ``attempts`` → ``{ok, changed, value, attempts}``)
idempotently sets a native control's value through the accessibility backend —
reading first and doing nothing if it already matches. It is the matching
``ac_ensure_field_value`` MCP tool and a Script Builder command under **Flow**.
:func:`ensure_state` / :func:`ensure_toggle` (which take arbitrary callables) are
the Python-API surface.
