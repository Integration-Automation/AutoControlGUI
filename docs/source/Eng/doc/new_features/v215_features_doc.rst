Set-of-Marks Label Layout (No Overlap, Readable Colour)
=======================================================

Set-of-Marks overlays a numbered label on every element so a vision model can
say "click 7". ``set_of_marks`` draws each label at a fixed offset, so on dense
UIs the numbers pile on top of each other (unreadable) and a dark label on a
dark element vanishes. ``marks_layout`` fixes both with pure geometry.

* :func:`place_labels` — greedy non-overlap placement: for each mark, try a ring
  of candidate positions around its box (above, below, inside; left/right
  aligned) and take the first that stays in bounds and clears every
  already-placed label.
* :func:`label_color` — pick the label text colour (black or white) with the
  better WCAG contrast against the element's background.

Pure standard library; reuses :func:`a11y_audit.contrast_ratio`. Fully testable
without rendering. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import mark_elements, place_labels, label_color

    marks = mark_elements(elements)            # [{id, bbox, ...}]
    layout = place_labels(marks, bounds=(1920, 1080))
    # [{'id': 1, 'label': [x, y, 22, 16], 'anchor': [bx, by]}, ...]

    label_color((30, 30, 30))     # {'rgb': [255, 255, 255], 'contrast': ...}

Feed the ``label`` boxes from :func:`place_labels` to your renderer instead of a
naive fixed offset, and pick each number's colour with :func:`label_color` so it
stays legible on its background. ``place_labels`` is deterministic and ordered by
the input marks, so the same screen always numbers the same way.

Executor commands
-----------------

``AC_place_labels`` (``marks`` JSON list + ``label_width`` / ``label_height`` /
``bounds`` ``[w, h]`` → ``{labels}``) and ``AC_label_color`` (``background``
``[r, g, b]`` → ``{rgb, contrast}``). They are the matching read-only ``ac_*``
MCP tools and Script Builder commands under **Image**.
