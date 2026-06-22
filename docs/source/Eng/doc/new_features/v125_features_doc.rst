Grid / Table Cell Addressing
============================

``anchor_locator`` does pairwise spatial relations (target *near* / *below* an
anchor) but nothing addresses a 2-D grid — "the cell at row 3, column 2" of a
table. Given the bounding boxes of the cells (from an image or OCR enumeration,
e.g. ``locate_all_image`` / ``find_text_matches``), this clusters them into rows
and columns and returns the requested cell's centre.

The clustering and lookup are pure (boxes in, grid / cell out) and fully
unit-testable; the box enumeration stays the caller's job, so nothing here needs a
real screen. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import cluster_grid, locate_cell

    boxes = [(10, 100, 20, 10), (110, 100, 20, 10), (210, 100, 20, 10),
             (10, 200, 20, 10), (110, 200, 20, 10), (210, 200, 20, 10)]

    locate_cell(boxes, row=1, col=2)
    # {'found': True, 'center': [220, 205], 'box': [210, 200, 20, 10],
    #  'row': 1, 'col': 2, 'rows': 2, 'cols': 3}

    cluster_grid(boxes)   # rows top-to-bottom, cells left-to-right

``cluster_grid`` sorts the boxes by centre-y, starts a new row when the gap
exceeds ``row_tolerance``, and orders each row's cells by centre-x.
``locate_cell`` returns the centre (ready to click) of the 0-based ``(row, col)``
cell, or ``{found: False, reason}`` when the index is out of range.

Executor commands
-----------------

``AC_grid_cell`` takes ``boxes`` (a JSON ``[[x, y, w, h], ...]`` list, e.g. from a
prior ``AC_locate_all_image`` step) plus ``row`` / ``col`` / ``row_tolerance`` and
returns the cell dict. It is exposed as the MCP tool ``ac_grid_cell`` and as a
Script Builder command under **Mouse**.
