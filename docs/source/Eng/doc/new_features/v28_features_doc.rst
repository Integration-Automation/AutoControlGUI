==================================================
New Features (2026-06-19) — Process-Doc (SOP) Generator
==================================================

Turn a recorded / authored action list into a numbered, human-readable
**standard operating procedure** — a structured step list plus an HTML
rendering (the UiPath Task-Capture deliverable) for runbooks and review.
Pure standard library; full stack.

.. contents::
   :local:
   :depth: 2


Usage
=====

::

    from je_auto_control import generate_sop, write_sop

    doc = generate_sop(actions, title="Invoice Login")
    doc["steps"]        # [{n, command, description, args}, ...]
    doc["html"]         # full HTML document (content escaped)
    write_sop(actions, "procedure.html", title="Invoice Login")

Each action is mapped to a human verb phrase (``AC_write`` → "Type text",
``AC_click_mouse`` → "Click the mouse", …) with the most descriptive
argument appended; unknown commands fall back to a readable form of the
name. User content is HTML-escaped. Exposed as ``AC_generate_sop`` /
``ac_generate_sop`` (writes a file when ``path`` is given, else returns the
structured document).
