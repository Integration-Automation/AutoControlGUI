Rich Clipboard — HTML (CF_HTML)
===============================

The base ``clipboard`` module handles plain text (``CF_UNICODETEXT``) and image
(``CF_DIB``) only. Pasting *formatted* content into Word / Outlook / a rich editor
needs the ``CF_HTML`` format, whose ``Version / StartHTML / EndHTML / StartFragment /
EndFragment`` **byte-offset** header is notoriously error-prone to build by hand.
``build_cf_html`` / ``parse_cf_html`` compute and recover that header in pure Python
(a fully unit-tested round-trip, correct across multi-byte UTF-8), and
``set_clipboard_html`` / ``get_clipboard_html`` wrap them over the Win32 clipboard.

The byte-offset math is platform-independent and headless-testable; only the actual
clipboard I/O is Windows (raising ``RuntimeError`` elsewhere, like the base module).
Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (build_cf_html, parse_cf_html,
                                 set_clipboard_html, get_clipboard_html)

    set_clipboard_html("<b>Bold</b> and <i>italic</i>",
                       fragment_plaintext="Bold and italic")   # Windows
    html = get_clipboard_html()                                 # Windows

    # The pure pieces work anywhere (e.g. to pre-build a payload):
    payload = build_cf_html("<p>hello</p>")     # bytes, valid CF_HTML
    assert parse_cf_html(payload) == "<p>hello</p>"

``build_cf_html`` returns valid ``CF_HTML`` UTF-8 bytes whose offsets point exactly at
the fragment; ``parse_cf_html`` recovers the fragment from bytes or text (preferring
the comment markers, falling back to the byte offsets). ``set_clipboard_html`` also
seeds plain text via ``fragment_plaintext`` so apps that ignore HTML still paste
something.

Executor commands
-----------------

``AC_set_clipboard_html`` (``html`` / ``fragment_plaintext`` → ``{set, length}``) and
``AC_get_clipboard_html`` (→ ``{found, html}``). They are exposed as the MCP tools
``ac_set_clipboard_html`` / ``ac_get_clipboard_html`` and as Script Builder commands
under **Data**.
