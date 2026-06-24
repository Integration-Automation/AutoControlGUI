Open Files / URLs with the Default App
======================================

The framework could launch a literal executable (``start_exe`` / ``shell_process``),
but not the single most common "hand off to another app" RPA step: open
``report.pdf`` with whatever app is registered for it, ``print`` a document, or
open a URL in the default browser. ``shell_open`` adds that, routed per-OS to
``os.startfile`` / ``open`` / ``xdg-open`` / ``webbrowser``.

* :func:`plan_open` — pure planner: classify the target (URL vs file path),
  validate it (URL scheme allow-list; ``realpath`` for files) and return the
  dispatch descriptor,
* :func:`open_path` — run the plan through an injectable ``opener`` sink (the real
  OS call by default).

Pure stdlib; the dispatch logic is unit-testable without launching anything via
the injectable ``opener``. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import open_path, plan_open

    open_path("report.pdf")                 # default PDF viewer
    open_path("invoice.pdf", verb="print")  # print it
    open_path("https://example.com")        # default browser

    plan_open("https://example.com")
    # {"kind": "url", "scheme": "https", "target": "...", "backend": "webbrowser",
    #  "verb": "open"}
    plan_open("report.pdf")
    # {"kind": "file", "target": "<realpath>", "backend": "startfile", ...}

A ``scheme://`` target (or ``mailto:`` / ``tel:``) is opened as a URL — only the
allow-listed schemes (``http`` / ``https`` / ``ftp`` / ``file`` / ``mailto`` /
``tel``) are accepted, anything else raises ``ValueError``. Everything else is a
file path (a Windows drive like ``C:\\…`` is correctly treated as a path, not a
scheme) and is ``realpath``-resolved. ``verb`` (``open`` / ``print`` / ``edit``)
applies to files on Windows.

Executor commands
-----------------

``AC_open_path`` (``target`` / ``verb`` → ``{opened}``) and ``AC_plan_open``
(``target`` / ``verb`` → the plan). They are exposed as the matching ``ac_*`` MCP
tools (``open_path`` side-effect-only, ``plan_open`` read-only) and as Script
Builder commands under **Shell**.
