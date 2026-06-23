Clipboard File-Drop List (CF_HDROP)
===================================

The clipboard layer carried text and images, and ``rich_clipboard`` added HTML, but the
framework could never put a *list of files* on the clipboard — the ``CF_HDROP`` payload
Explorer reads when you copy files and ``Ctrl+V`` them elsewhere as a real file copy.
Building that blob is fiddly: a fixed 20-byte ``DROPFILES`` header followed by a
double-null-terminated (UTF-16 by default) path list, with the header's ``pFiles`` offset
pointing at the list. ``clipboard_files`` isolates that error-prone packing.

The packing lives in pure, fully unit-testable ``build_dropfiles`` / ``parse_dropfiles``
byte functions (no device, any platform), with thin Windows-only ``set_clipboard_files`` /
``get_clipboard_files`` wrappers on top — the same split ``rich_clipboard`` uses for
``CF_HTML``. The pure functions import no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (build_dropfiles, parse_dropfiles,
                                 set_clipboard_files, get_clipboard_files)

    # put two files on the clipboard, ready to paste into Explorer (Windows)
    set_clipboard_files([r"C:\reports\q1.pdf", r"C:\reports\q2.pdf"])
    print(get_clipboard_files())

    # the byte layer is testable without a clipboard at all
    blob = build_dropfiles([r"C:\a\one.txt"], point=(10, 20))
    assert parse_dropfiles(blob)["paths"] == [r"C:\a\one.txt"]

``build_dropfiles(paths, *, point=(0, 0), wide=True, non_client=False)`` returns the raw
``DROPFILES`` bytes; ``parse_dropfiles`` reverses it into
``{paths, point, wide, non_client}``. ``set_clipboard_files`` / ``get_clipboard_files`` put
and read the list via the Windows clipboard (``get`` returns ``None`` when no file list is
present).

Executor commands
-----------------

``AC_set_clipboard_files`` (``paths`` → ``{set, count}``) and ``AC_get_clipboard_files``
(→ ``{found, paths}``). They are exposed as the MCP tools ``ac_set_clipboard_files`` /
``ac_get_clipboard_files`` and as Script Builder commands **Set Clipboard Files** /
**Get Clipboard Files** under **Data**.
