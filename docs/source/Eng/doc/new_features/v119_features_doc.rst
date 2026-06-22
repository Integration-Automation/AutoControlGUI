Hold Key / Auto-Repeat
======================

``type_keyboard`` is an instant down+up and ``input_macro.run_sequence`` can
hand-roll a press / wait / release, but there was no primitive for "hold this key
for N seconds" (game movement, hold-to-scroll) or "send it at R presses per
second" (auto-repeat).

:func:`plan_key_hold` builds the deterministic op-plan (pure, unit-testable);
:func:`hold_key` dispatches it through an injectable ``sink`` and ``sleep`` so it
is tested without real input or real waiting. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import hold_key, plan_key_hold

    hold_key("key_d", duration_s=1.5)              # press, hold 1.5s, release
    hold_key("key_down", duration_s=2.0, rate_hz=20)   # 40 key events @ 50ms

    plan_key_hold("space", 1.0)
    # [{'op': 'press', 'key': 'space'},
    #  {'op': 'wait', 'seconds': 1.0},
    #  {'op': 'release', 'key': 'space'}]

With ``rate_hz`` unset the key is pressed, held for ``duration_s``, then released.
With ``rate_hz`` set it is sent as ``round(duration_s * rate_hz)`` discrete key
events spaced ``1 / rate_hz`` apart — simulated auto-repeat for movement / scroll
loops. A non-positive duration or rate raises ``ValueError``. ``hold_key`` routes
the ``wait`` steps to ``sleep`` and the key steps to ``sink``, both injectable.

Executor commands
-----------------

``AC_hold_key`` takes ``key`` plus ``duration_s`` and an optional ``rate_hz`` and
returns ``{ops, plan}``. It is exposed as the MCP tool ``ac_hold_key`` and as a
Script Builder command under **Keyboard**.
