Rich Clipboard Formats — RTF and CSV/TSV
========================================

``rich_clipboard`` added ``CF_HTML`` for rich paste into Word / Outlook, but two
other cross-application clipboard formats were still missing:

* **RTF** (``"Rich Text Format"``) — the format almost every rich editor accepts
  for styled paste. ``build_rtf`` / ``rtf_to_text`` build and strip RTF control
  words and ``\uNNNN`` / ``\'XX`` escapes in pure Python, with a fully
  unit-testable round-trip.
* **CSV / TSV** (the registered ``"Csv"`` format Excel reads) — ``rows_to_csv`` /
  ``csv_to_rows`` are a thin, delimiter-parametrised wrapper over the stdlib
  ``csv`` module, so a table can be put on / read off the clipboard.

The codecs are platform-independent and headless-testable; only the actual
clipboard I/O is Win32 (raising ``RuntimeError`` elsewhere, like the base
``clipboard`` module), and the byte transfer is a single generic helper shared by
both formats. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (build_rtf, rtf_to_text, rows_to_csv,
                                 csv_to_rows, set_clipboard_rtf, set_clipboard_csv)

    rtf = build_rtf("Hello\nWorld")          # minimal valid RTF document
    rtf_to_text(rtf)                          # -> "Hello\nWorld"

    rows_to_csv([["a", "b"], ["1", "2"]])     # 'a,b\r\n1,2\r\n'
    csv_to_rows("a,b\r\n1,2\r\n")             # [["a", "b"], ["1", "2"]]

    set_clipboard_rtf("Paste me as styled text")   # Windows
    set_clipboard_csv([["Name", "Qty"], ["Pen", "3"]], delimiter="\t")  # TSV

``build_rtf`` escapes braces / backslashes, turns newlines into ``\par`` and
non-ASCII characters into ``\uNNNN?`` escapes (the output is pure ASCII).
``set_clipboard_rtf`` / ``set_clipboard_csv`` also seed plain text by default so
plain editors still paste something; ``get_clipboard_rtf`` returns the raw RTF
string (feed it to ``rtf_to_text``) and ``get_clipboard_csv`` returns rows.

Executor commands
-----------------

``AC_set_clipboard_rtf`` / ``AC_get_clipboard_rtf`` / ``AC_set_clipboard_csv`` /
``AC_get_clipboard_csv`` (the sets take ``text`` / ``rows`` + ``delimiter``). They
are exposed as the matching ``ac_*`` MCP tools (the sets side-effect-only, the
gets read-only) and as Script Builder commands under **Data**.
