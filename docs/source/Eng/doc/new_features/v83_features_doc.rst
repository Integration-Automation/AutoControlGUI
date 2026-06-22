Dataset Diff (Row-Set Change Report)
====================================

The framework diffs *screens/snapshots* (``screen_state.diff_snapshots``,
``diff_screenshots``) but had nothing to diff two **tabular** row-sets by key —
the standard "what changed between yesterday's and today's extract" report.
This keys both sides, then reports added / removed / changed / unchanged rows
and per-cell changes.

Pure standard library; imports no ``PySide6``. Every function is pure (rows in,
dict/list out), so it is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import diff_rows, cell_changes, summarize_diff, load_rows

    old = load_rows("yesterday.csv")
    new = load_rows("today.csv")

    diff = diff_rows(old, new, "id")          # or ["region", "id"]
    summarize_diff(diff)                       # {added, removed, changed, unchanged}

    for change in cell_changes(old, new, "id"):
        print(change["key"], change["column"], change["old"], "->", change["new"])

``diff_rows`` keys both row-sets and returns ``{added, removed, changed,
unchanged}``: ``added`` / ``removed`` / ``unchanged`` are row lists, while
``changed`` holds ``{key, old, new}`` entries (the key is a scalar for a single
column or a list for a composite key). On duplicate keys the last row wins.
``cell_changes`` expands the changed rows into ``{key, column, old, new}``
records. ``summarize_diff`` counts each bucket.

Executor commands
-----------------

``AC_diff_rows`` returns ``{diff, summary}`` for ``old_rows`` / ``new_rows`` and
a ``key`` (column name or JSON list). ``AC_cell_changes`` returns
``{changes}``. Both are exposed as MCP tools (``ac_diff_rows`` /
``ac_cell_changes``) and as Script Builder commands under **Data**.
