Fuse & Order On-Screen Element Boxes
====================================

``set_of_marks.mark_elements`` numbers a single, already-clean element list — but
nothing *produces* that list. A real screen parse yields three overlapping sources
(OCR text boxes, icon/shape boxes, accessibility boxes) with heavy duplication and no
consistent order. This module is the missing connective tissue between the locators
(``locate_text``, ``find_shapes``, the a11y tree) and ``set_of_marks``: de-duplicate
by overlap, union the sources keeping the most trustworthy box, and sort into reading
order with a stable index.

Every box is a plain ``dict`` with ``x, y, width, height`` (plus any extra keys such
as ``text`` / ``source`` / ``score``), so the whole module is pure-stdlib and fully
unit-testable. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import iou, merge_boxes, fuse_elements, reading_order

    iou(box_a, box_b)                          # overlap of two boxes, 0..1
    deduped = merge_boxes(raw_boxes, iou_threshold=0.9)

    # Union three detector outputs; on overlap the a11y box wins, then OCR, then icon.
    elements = fuse_elements(ocr_boxes=ocr, icon_boxes=icons, a11y_boxes=tree)

    # Sort top-to-bottom, left-to-right and add an "index" to each.
    for el in reading_order(elements):
        print(el["index"], el.get("text"), el["x"], el["y"])

``iou`` returns the intersection-over-union of two boxes. ``merge_boxes`` keeps the
largest of any cluster overlapping above ``iou_threshold``. ``fuse_elements`` tags
each input with its ``source``, then drops cross-source overlaps preferring
``source_priority`` (default ``a11y`` > ``ocr`` > ``icon``, then larger area).
``reading_order`` bands rows within ``row_tol`` pixels, orders by ``x`` within each
row, and returns new dicts carrying a sequential ``index``.

Executor commands
-----------------

``AC_fuse_elements`` (``ocr`` / ``icon`` / ``a11y`` JSON arrays + ``iou_threshold``
→ ``{count, elements}``) and ``AC_reading_order`` (``elements`` + ``row_tol`` →
``{count, elements}``). They are exposed as the MCP tools ``ac_fuse_elements`` /
``ac_reading_order`` and as Script Builder commands under **Image**.
