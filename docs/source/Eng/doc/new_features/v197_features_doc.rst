Table Headers + Cell Addressing (UIA TablePattern)
==================================================

``read_control_table`` (GridPattern) dumps a flat 2-D list of cell names with **no
header labels and no way to address a single cell by (header, row)** — so you can
*dump* a grid but not actually *test* one. ``table_pattern`` adds the missing
half:

* :func:`table_headers` — the row / column header labels (TablePattern),
* :func:`table_cell` — the cell at ``(row, column)`` with its span
  (GridPattern.GetItem + GridItemPattern),
* :func:`cell_by_header` — read the cell at ``(row, "Column Header")``, so you can
  assert "the Status column of row 5 says Shipped" without guessing indices.

Each is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam — headless-testable by injecting a fake backend; the real UIA calls live in
the Windows backend. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import table_headers, table_cell, cell_by_header

    table_headers(name="Orders")
    # {"columns": ["Order", "Status", "Total"], "rows": [...]}

    table_cell(0, 1, name="Orders")
    # {"value": "Shipped", "row": 0, "column": 1, "row_span": 1, "column_span": 1}

    cell_by_header(0, "Status", name="Orders")          # "Shipped"

The table is located by ``name`` / ``role`` / ``app_name`` / ``automation_id``
(same as ``read_control_table``). ``table_headers`` returns
``{columns, rows}`` (or ``None``); ``table_cell`` returns the cell record (or
``None``); ``cell_by_header`` resolves the column index from the headers and
returns the cell value (``None`` if the header or cell isn't found).

Executor commands
-----------------

``AC_table_headers`` (``{found, headers}``), ``AC_table_cell`` (``row`` /
``column`` → ``{found, cell}``) and ``AC_cell_by_header`` (``row`` /
``column_header`` → ``{found, value}``). They are exposed as read-only ``ac_*``
MCP tools and as Script Builder commands under **Native UI**.
