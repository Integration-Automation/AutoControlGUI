Unicode Text Entry (Emoji / CJK)
================================

``write`` types through the platform virtual-key table and *raises* on any
character outside it — emoji, CJK, many accented letters — so non-ASCII text entry
was impossible through the normal path. The reliable, cross-platform way to enter
arbitrary Unicode is to put it on the clipboard and paste it.

:func:`plan_paste` builds the deterministic op-plan and :func:`unicode_code_units`
splits text into UTF-16 code units (for a backend that can do
``KEYEVENTF_UNICODE``); both are pure and unit-testable. :func:`type_unicode`
dispatches the paste plan through an injectable ``sink`` so it is tested without
touching the real clipboard. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import type_unicode, plan_paste, unicode_code_units

    type_unicode("café 🚀 値")              # clipboard set + Ctrl+V
    type_unicode("値", modifier="command")  # macOS

    unicode_code_units("🚀")               # [0xD83D, 0xDE80] (surrogate pair)
    plan_paste("hi")
    # [{'op': 'set_clipboard', 'text': 'hi'},
    #  {'op': 'hotkey', 'keys': ['ctrl', 'v']}]

``type_unicode`` sets the clipboard to the text and sends the paste hotkey
(``modifier`` defaults to ``"ctrl"``; use ``"command"`` on macOS), so it enters
*any* text regardless of keyboard layout — emoji, CJK, RTL, accented. It returns
the dispatched plan plus the UTF-16 code-unit count. ``unicode_code_units`` is
provided for backends that want to inject code units directly.

Executor commands
-----------------

``AC_type_unicode`` takes ``text`` plus an optional ``modifier`` and returns
``{ops, plan, code_units}``. It is exposed as the MCP tool ``ac_type_unicode`` and
as a Script Builder command under **Keyboard**.
