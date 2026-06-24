Clipboard Format Inspection (classify / diff available formats)
===============================================================

The clipboard usually holds the *same* content in several formats at once — a
copy from Word offers ``CF_UNICODETEXT`` + ``HTML Format`` + ``Rich Text Format``,
a file copy offers ``CF_HDROP``, a screenshot offers ``CF_DIB``. Knowing *which
formats are present* (without consuming any of them) tells an automation what it
can paste, and comparing two snapshots detects when the clipboard's shape
changed. ``clipboard_formats`` adds:

* :func:`classify_format` / :func:`classify_formats` — map standard ``CF_*`` ids
  and registered format names to friendly categories (text / image / files /
  html / rtf / csv / audio / …),
* :func:`diff_formats` — a pure monitor primitive: ``{added, removed, changed}``
  between two snapshots,
* :func:`list_clipboard_formats` / :func:`clipboard_formats` — enumerate the live
  clipboard (``EnumClipboardFormats``) and classify it.

The classifier and diff are pure functions (unit-testable on any platform); only
the live enumeration is Win32 (raising ``RuntimeError`` elsewhere). Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (classify_formats, diff_formats,
                                 clipboard_formats)

    classify_formats([13, {"id": 49383, "name": "HTML Format"}])
    # {"categories": ["html", "text"], "has_text": True, "has_image": False, ...}

    diff_formats([13, 1], [13, 15])     # {"added": [files], "removed": [text], ...}

    clipboard_formats()                  # live clipboard summary (Windows)

A descriptor is an id (``13``), an ``{"id": ..., "name": ...}`` dict, or an
``(id, name)`` tuple. A registered ``name`` takes priority over the id, since
registered formats have dynamic ids (``>= 0xC000``). Unrecognised formats are
``"other"``.

Executor commands
-----------------

``AC_clipboard_formats`` (live, Windows), ``AC_classify_formats`` (``formats``)
and ``AC_diff_formats`` (``before`` / ``after``) — the latter two are pure and
run anywhere. They are exposed as read-only ``ac_*`` MCP tools and as Script
Builder commands under **Data**.
