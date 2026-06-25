Live IME State for Safe CJK Entry
=================================

Typing into a CJK / Japanese / Korean field is unsafe while an IME (input method
editor) is *composing*: the candidate text has not been committed yet, so
reading the field back returns half-entered glyphs and the next keystroke edits
the composition instead of the field. ``text_unicode`` (``VK_PACKET``) is blind
to this. ``ime_state`` exposes the live composition and conversion state so a
flow can wait for the IME to commit before it reads or acts.

* :func:`ime_state` — ``{open, composing, composition, conversion,
  conversion_flags}`` for the focused window's IME, through an injectable
  ``reader``.
* :func:`is_composing` — ``True`` while the IME has an uncommitted composition.
* :func:`wait_for_composition_commit` — block until composition ends (or a
  timeout), with injectable ``clock`` / ``sleep`` / ``reader``.
* :func:`decode_conversion_mode` — pure: the IMM32 ``IME_CMODE_*`` conversion
  bitmask to ``{native, katakana, full_shape, roman, char_code}``.

The default ``reader`` queries Windows IMM32 (``ImmGetContext`` /
``ImmGetOpenStatus`` / ``ImmGetConversionStatus`` / ``ImmGetCompositionStringW``)
read-only; all decoding / waiting logic runs through the injectable seam, so it
is fully testable without an IME. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        ime_state, is_composing, wait_for_composition_commit,
    )

    # Before reading a CJK field, make sure the IME has committed
    if wait_for_composition_commit(timeout_s=3):
        value = read_field()

    is_composing()   # True while candidate text is still on screen
    ime_state()      # {'open': True, 'composing': True, 'composition': 'あ', ...}

For tests (or any non-Windows host) pass a ``reader`` — a
``() -> {open, conversion, composition}``:

.. code-block:: python

    busy = lambda: {"open": True, "conversion": 0, "composition": "あ"}
    is_composing(reader=busy)            # True
    ime_state(reader=busy)["composition"]  # 'あ'

Executor commands
-----------------

``AC_ime_state`` (→ the full state), ``AC_is_composing`` (→ ``{composing}``),
``AC_wait_for_composition_commit`` (``timeout`` / ``interval`` →
``{committed}``) and ``AC_decode_conversion_mode`` (``flags`` → the decoded
modes). They are exposed as the matching read-only ``ac_*`` MCP tools and as
Script Builder commands under **Shell**.
