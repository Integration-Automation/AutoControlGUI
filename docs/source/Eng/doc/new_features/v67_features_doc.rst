Text Diff, Patch & Three-Way Merge
==================================

``difflib`` *generates* a unified diff but the standard library cannot *apply*
one, and there was no three-way merge anywhere — so updating a ``.received``
artifact, replaying a recorded text edit, or merging two edits of a base file
had no headless primitive. This adds the missing pieces. It complements
``utils/json_patch`` (structured JSON); this is line-based text.

Pure standard library (``difflib`` + ``re``); imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import unified_diff, apply_unified, three_way_merge

    diff = unified_diff(original, edited)
    restored = apply_unified(original, diff)        # == edited

    merge = three_way_merge(base, ours, theirs)
    if merge.clean:
        save(merge.text)
    else:
        print(merge.conflicts, "conflict(s)")       # text has <<<<<<< markers

``unified_diff`` wraps ``difflib``; ``apply_unified`` is the missing applier —
it walks each ``@@`` hunk, verifies the context/removed lines match, and raises
``PatchApplyError`` on mismatch. ``three_way_merge`` merges line-based:
non-overlapping edits from each side combine cleanly; if both sides edit the
same region (and differ), it emits a conflict block with
``<<<<<<< / ======= / >>>>>>>`` markers and reports ``clean=False``. Trivial
cases (one side unchanged, or identical edits) resolve automatically.

Executor commands
-----------------

``AC_unified_diff`` (``{diff}``), ``AC_apply_unified`` (``{result}``) and
``AC_three_way_merge`` (``{text, clean, conflicts}``). Each is also exposed as
an MCP tool (``ac_unified_diff`` / ``ac_apply_unified`` / ``ac_three_way_merge``)
and as a Script Builder command under **Data**.
