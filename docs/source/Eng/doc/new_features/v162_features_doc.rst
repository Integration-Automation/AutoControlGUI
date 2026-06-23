Fill a Ruling-Line Grid With OCR Text (Addressable Tables)
==========================================================

``edge_lines.find_grid`` recovers a bordered table's geometry — ``{rows: [y…], cols: [x…],
cells: […]}`` — but the cells come back *empty* (just rectangles between the ruling lines).
OCR gives the text but no table structure. Nothing joined the two, so reading a bordered
table meant hand-rolling the box→cell assignment. ``table_grid_fill`` drops OCR text boxes
into the grid and returns an addressable ``R x C`` table.

Each box is assigned to the cell its centre falls in (gated by an overlap fraction so a box
straddling a thin rule is not double counted); text within a cell is concatenated in reading
order; boxes that straddle multiple cells are reported as merged-cell candidates. The result
converts straight to records or CSV.

Pure-stdlib geometry over plain dicts (the grid + the boxes) — no image, no OCR engine, no
device. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (find_grid, find_text_lines,  # producers
                                 populate_table, assign_text_to_grid,
                                 table_to_records, table_to_csv)

    grid = find_grid(region=[0, 0, 800, 400])      # ruling-line geometry
    boxes = [{"x": 10, "y": 5, "width": 60, "height": 20, "text": "Name"}, ...]

    table = assign_text_to_grid(grid, boxes)        # [["Name","Age"], ["Ann","30"]]
    records = table_to_records(table)               # [{"Name": "Ann", "Age": "30"}]
    csv_text = table_to_csv(table)

    full = populate_table(grid, boxes)              # {n_rows, n_cols, cells, spans}

``assign_text_to_grid`` returns the 2-D text table; ``populate_table`` returns the richer
``{n_rows, n_cols, cells:[{row, col, text}], spans:[{row, col, row_span, col_span, text}]}``.
``table_to_records`` uses the first row as headers; ``table_to_csv`` renders CSV. Boxes accept
either ``{x, y, width, height}`` or ``{left, top, right, bottom}`` plus a ``text`` field.

Executor command
----------------

``AC_populate_table`` (``grid`` / ``text_boxes`` / ``overlap`` → ``{n_rows, n_cols, cells,
spans}``) is exposed as the MCP tool ``ac_populate_table`` (read-only) and as the Script
Builder command **Fill Table From Grid + OCR** under **OCR**.
