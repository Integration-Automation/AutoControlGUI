Form Field Association (Multi-Direction) + Checkbox State
=========================================================

``ocr/structure`` recognises a label only if its text ends in ``:`` and pairs it with the
*immediately next* cell — it cannot handle a label sitting *above* its value, a two-column
key/value layout, right-aligned values, or any widget that isn't a text cell, and it has no
notion of checkbox / radio state at all. ``form_fields`` generalises this: it pairs each
label with the nearest aligned value in any of several *directions* (right, below), matches
free-standing widgets (checkboxes, radios, inputs) to their nearest label, and reads a
checkbox's checked state from its fill ratio.

The association is pure-stdlib over plain box dicts (fully unit-testable, no image); only
``checkbox_state`` touches pixels, isolated behind the shared ``visual_match`` gray loader so
tests can pass a synthetic array. Reuses ``table_grid_fill``'s box-bounds reader. Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (associate_fields, match_labels_to_widgets,
                                 checkbox_state)

    fields = associate_fields(ocr_boxes, directions=("right", "below"))
    # [{"label": "Name", "value": "Ann", "direction": "right", "gap": 20, ...}]

    pairs = match_labels_to_widgets(label_boxes, checkbox_boxes)
    # [{"widget": {...}, "label": "Accept terms", "distance": 22}]

    state = checkbox_state(screenshot, checkbox_box)   # "checked" | "unchecked"

``associate_fields`` treats boxes whose text ends in ``:`` as labels and pairs each with the
nearest value box in the requested directions (within ``max_gap``), returning
``{label, value, direction, gap, label_box, value_box}``. ``match_labels_to_widgets`` assigns
each widget to its nearest label by centre distance. ``checkbox_state`` returns
``"checked"`` / ``"unchecked"`` from the dark-pixel fill ratio of the box (image is injectable
— path / ndarray / PIL).

Executor commands
-----------------

``AC_associate_fields`` (``text_boxes`` / ``directions`` / ``max_gap`` → ``{count, fields}``)
and ``AC_match_labels_to_widgets`` (``labels`` / ``widgets`` → ``{count, pairs}``). They are
exposed as the MCP tools ``ac_associate_fields`` / ``ac_match_labels_to_widgets`` (read-only)
and as the Script Builder commands **Associate Form Fields** / **Match Labels To Widgets**
under **OCR**.
