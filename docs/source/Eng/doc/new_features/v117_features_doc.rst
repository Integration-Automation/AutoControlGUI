Clear-Then-Type Field Entry
===========================

Setting a field's value reliably means *clearing* whatever is there first, then
entering the new text — otherwise automation appends to or corrupts the existing
content. The framework has ``write`` (types, but raises on emoji / CJK / chars
outside the layout table) and ``set_clipboard`` / ``hotkey`` separately, but no
single "focus → clear → set value" primitive and no paste strategy for text that
``write`` cannot type. This adds the Playwright ``fill`` idiom.

:func:`plan_field_set` builds the deterministic op-plan (pure, unit-testable);
:func:`set_field_text` dispatches it through an injectable ``sink`` so it is
tested without real input. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import set_field_text, plan_field_set

    set_field_text("new value")                       # select-all, delete, type
    set_field_text("café 🚀", paste=True)             # via clipboard (Unicode-safe)
    set_field_text("appended", clear="none")          # no clear, just type
    set_field_text("値", paste=True, modifier="command")   # macOS

    plan_field_set("hi")
    # [{'op': 'hotkey', 'keys': ['ctrl', 'a']},
    #  {'op': 'key', 'key': 'delete'},
    #  {'op': 'type', 'text': 'hi'}]

``clear`` is ``"select_all"`` (the ``modifier``+A then Delete clear) or
``"none"``. ``paste=True`` enters the text through the clipboard (``modifier``+V)
— the reliable path for Unicode / emoji / CJK that ``write`` cannot type — rather
than typing key by key. ``modifier`` is the platform command key (``"ctrl"``; use
``"command"`` on macOS). An unknown ``clear`` mode raises ``ValueError``.

Executor commands
-----------------

``AC_set_field_text`` takes ``text`` plus ``clear`` / ``paste`` / ``modifier`` and
returns ``{ops, plan}``. It is exposed as the MCP tool ``ac_set_field_text`` and
as a Script Builder command under **Keyboard**.
