Resolve the App Registered for a File Type
==========================================

:func:`open_path` (``shell_open``) opens a file with whatever app is registered
for it; ``file_assoc`` answers the inverse, read-only question — *which* app is
that? Given ``report.pdf`` (or a bare ``.pdf`` / ``pdf``) it returns the
registered executable, the friendly app name, the open command line and the MIME
content type, via the Windows ``AssocQueryStringW`` shell API.

* :func:`normalize_ext` — pure helper turning a path / ``.ext`` / bare ``ext``
  into a lowercased ``.ext``,
* :func:`file_association` — run the lookup through an injectable ``resolver``
  seam (the real shell API by default).

The assembly logic is unit-testable without Windows via the injectable
``resolver``. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import file_association, normalize_ext

    normalize_ext("report.PDF")     # ".pdf"
    normalize_ext("archive.tar.gz") # ".gz"

    file_association("report.pdf")
    # {"ext": ".pdf", "command": "...AcroRd32.exe \"%1\"",
    #  "exe": "...AcroRd32.exe", "friendly": "Adobe Acrobat",
    #  "content_type": "application/pdf"}

The app fields are ``None`` when nothing is registered for the type. This is the
natural companion to :func:`open_path`: ``file_association`` tells you *what*
would open a file (assert "PDFs open in Acrobat, not the browser"), and
``open_path`` actually opens it. The live lookup uses the Windows shell API; on
other platforms pass your own ``resolver``.

Executor commands
-----------------

``AC_normalize_ext`` (``target`` → ``{ext}``, pure) and ``AC_file_association``
(``target`` → the association dict). They are exposed as the matching ``ac_*``
MCP tools (both read-only) and as Script Builder commands under **Shell**.
