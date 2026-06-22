==================================================
New Features (2026-06-19) — CI Annotations & Clipboard History
==================================================

Two pure-standard-library utilities: emit CI annotations from results, and
keep a searchable clipboard history. Full stack.

.. contents::
   :local:
   :depth: 2


CI workflow annotations
======================

::

    from je_auto_control import emit_annotations

    emit_annotations([
        {"level": "error", "message": "step failed",
         "file": "flows/login.json", "line": 12, "title": "Login"},
    ])
    # prints: ::error file=flows/login.json,line=12,title=Login::step failed

Converts result dicts (``{level, message, file?, line?, col?, title?}``)
into GitHub Actions workflow commands so failures surface **inline** in a PR
— no third-party reporter action required. ``level`` is ``error`` /
``warning`` / ``notice``; values are escaped per GitHub's rules. Exposed as
``AC_ci_annotations`` / ``ac_ci_annotations``.


Clipboard history
================

::

    from je_auto_control import ClipboardHistory, default_clipboard_history

    default_clipboard_history.start()      # poll the clipboard in the background
    default_clipboard_history.search("invoice")
    default_clipboard_history.get(0)        # most recent entry

A capped, newest-first ring buffer of distinct clipboard text entries with
``add`` / ``snapshot`` / ``get`` / ``search`` / ``clear`` and an optional
background poller (``start`` / ``stop`` / ``capture_once``). Exposed as
``AC_clip_history_capture`` / ``AC_clip_history_list`` /
``AC_clip_history_search`` / ``AC_clip_history_start`` /
``AC_clip_history_stop`` (and ``ac_clip_history_*``).
