Whitespace-Projection Columns (Borderless Tables)
=================================================

``ocr/structure`` detects tables only when *every* row's cell-left-x matches within a
tolerance — it collapses on ragged or borderless tables, right-aligned numeric columns, or
any row with a missing cell. ``edge_lines.find_grid`` needs ruling lines, so a table drawn
purely with whitespace has no grid at all. ``column_layout`` finds columns the robust way the
layout-analysis literature uses: by the *gaps*. It projects the OCR boxes onto the x-axis (an
ink-density profile), reads off the persistent empty vertical bands as column gutters, assigns
each box a column index, and buckets rows by vertical spacing to emit a borderless table.

Pure-stdlib over plain box dicts (a difference-array projection — no numpy), so it is fully
unit-testable with no image and no OCR engine. Reuses ``table_grid_fill``'s box-bounds reader.
Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (detect_borderless_table, column_gutters,
                                 assign_columns, vertical_projection)

    table = detect_borderless_table(ocr_boxes)
    # {"n_rows": 3, "n_cols": 2, "rows": [["Name","Age"],["Ann","30"],["Bob","25"]],
    #  "columns": [{"start": 70, "end": 120, "width": 50}]}

    gutters = column_gutters(ocr_boxes, min_gap=8)   # empty vertical bands
    tagged = assign_columns(ocr_boxes)               # each box + "column" index
    profile = vertical_projection(ocr_boxes)         # ink density per x

``vertical_projection`` returns the per-x ink-density profile; ``column_gutters`` returns the
interior empty bands ``[{start, end, width}]`` at least ``min_gap`` wide; ``assign_columns``
tags every box with a 0-based ``column``; ``detect_borderless_table`` combines columns (from
gutters) with rows (from vertical spacing) into ``{n_rows, n_cols, rows, columns}``, or
``None`` when fewer than ``min_cols`` columns / ``min_rows`` rows are found. Boxes accept
``{x, y, width, height}`` or ``{left, top, right, bottom}`` plus an optional ``text``.

Executor commands
-----------------

``AC_detect_borderless_table`` (``boxes`` / ``page_width`` / ``min_gap`` / ``min_cols`` /
``min_rows`` → ``{found, table}``) and ``AC_column_gutters`` (``boxes`` / ``page_width`` /
``min_gap`` → ``{count, gutters}``). They are exposed as the MCP tools
``ac_detect_borderless_table`` / ``ac_column_gutters`` (read-only) and as the Script Builder
commands **Detect Borderless Table** / **Column Gutters (whitespace)** under **OCR**.
