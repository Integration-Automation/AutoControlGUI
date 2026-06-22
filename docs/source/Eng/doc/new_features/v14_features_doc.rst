============================================
New Features (2026-06-19) — Office I/O
============================================

Headless read/write for Office documents — Excel (``.xlsx``), Word
(``.docx``), and PowerPoint (``.pptx``) — so flows can ingest a row-set or
emit a report without driving the GUI. Wired through the full stack
(facade, ``AC_*`` executor commands, MCP tools, Script Builder).

The backing libraries (``openpyxl`` / ``python-docx`` / ``python-pptx``)
are an **optional** dependency::

    pip install je_auto_control[office]

Each function raises a clear ``RuntimeError`` if its library is missing,
so the core package stays lean and ``import je_auto_control`` pulls none of
them.

.. contents::
   :local:
   :depth: 2


Excel
=====

::

    from je_auto_control import read_workbook, write_workbook

    write_workbook("people.xlsx", [{"name": "Ada", "age": 36}], sheet="P")
    rows = read_workbook("people.xlsx", sheet="P")   # [{'name': 'Ada', ...}]

The first row supplies the dict keys; ``sheet`` defaults to the active
sheet. Commands: ``AC_read_workbook`` / ``AC_write_workbook`` (and
``ac_read_workbook`` / ``ac_write_workbook``).


Word
====

::

    from je_auto_control import read_document, write_document

    write_document("report.docx", ["Title", "First line", "Second line"])
    paragraphs = read_document("report.docx")["paragraphs"]

Commands: ``AC_read_document`` / ``AC_write_document``.


PowerPoint
==========

::

    from je_auto_control import read_presentation, write_presentation

    write_presentation("deck.pptx", [
        {"title": "Intro", "body": ["bullet one", "bullet two"]},
    ])
    slides = read_presentation("deck.pptx")["slides"]   # per-slide text runs

Each slide spec is ``{title, body:[...]}`` on a "Title and Content"
layout. Commands: ``AC_read_presentation`` / ``AC_write_presentation``.
