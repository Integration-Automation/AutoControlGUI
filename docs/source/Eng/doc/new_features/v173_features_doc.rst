Column-Aware Reading Order (XY-Cut)
===================================

``element_parse.reading_order`` is a flat top-to-bottom / left-to-right sort — it interleaves
columns on any multi-column page (the well-documented naive-sort failure: it reads row 1 of
column A, then row 1 of column B, then row 2 of A …). ``reading_flow`` recovers the correct
order with recursive **XY-cut**: it repeatedly splits the boxes at the widest whitespace valley
(a vertical gutter → columns, a horizontal gutter → rows / blocks), so a two-column layout is
read *down* column A fully, then column B.

The public flattener is named ``flow_order`` to sit *beside* — not shadow —
``element_parse.reading_order``; it returns the same ``index``-tagged element contract, so it is
a drop-in column-aware upgrade. Pure-stdlib geometry over plain box dicts (no image, no OCR
engine); reuses ``table_grid_fill``'s box-bounds reader. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import flow_order, xy_cut, to_blocks

    # two columns, two rows each: reads A1, A2, B1, B2 — not A1, B1, A2, B2
    for element in flow_order(ocr_boxes, min_gap=12):
        print(element["index"], element["text"])

    tree = xy_cut(ocr_boxes, min_gap=12)     # {type, axis, children|boxes}
    blocks = to_blocks(tree)                  # leaf blocks in reading order

``flow_order`` returns the boxes in column-aware reading order, each tagged with an ``index``.
``xy_cut`` returns the recursive region tree (each node is a ``split`` on ``axis`` ``"x"`` /
``"y"`` or a ``leaf`` of boxes). ``to_blocks`` flattens the tree to its leaf blocks in order.
``min_gap`` is the smallest whitespace valley treated as a column / row break.

Executor commands
-----------------

``AC_flow_order`` (``boxes`` / ``min_gap`` → ``{count, elements}``) and ``AC_xy_cut``
(``boxes`` / ``min_gap`` → ``{tree}``). They are exposed as the MCP tools ``ac_flow_order`` /
``ac_xy_cut`` (read-only) and as the Script Builder commands **Reading Order (column-aware)** /
**XY-Cut Region Tree** under **OCR**.
