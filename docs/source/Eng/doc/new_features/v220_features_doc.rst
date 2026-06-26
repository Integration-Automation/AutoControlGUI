Template-Free Element Proposal (Pixels to Elements)
===================================================

Set-of-Marks, ``observation`` and the grounding helpers all assume you already
have a list of element boxes — but on a screen the framework doesn't model
(a game, a custom-drawn app, a remote desktop) there is no accessibility tree to
provide one. ``element_proposal`` builds that top-of-funnel list from pixels:
detect candidate *widget* boxes (closed-edge blobs) and *text* boxes
(:func:`text_regions.find_text_regions`), fuse them — dropping widget boxes that
are really just text — and return them in reading order, each tagged ``text`` or
``widget``.

* :func:`propose_elements` — the full pixel-to-elements pipeline.
* :func:`tag_kinds` — pure: label fused boxes ``text`` / ``widget`` by source and
  keep their reading-order ``index``.

The fusion / cross-check / ordering reuse :mod:`element_parse` — the ``ocr`` >
``icon`` source priority *is* the "drop widget-that-is-really-text" check — and
the text detection reuses :mod:`text_regions`. ``cv2`` is imported lazily so the
module stays importable; :func:`tag_kinds` is pure and fully testable. Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import propose_elements, mark_elements

    # No accessibility tree? Propose elements straight from the screen:
    elements = propose_elements(min_area=120)
    # [{'box': [x, y, w, h], 'kind': 'widget', 'index': 0}, ...]

    # Feed them to Set-of-Marks like any other element list:
    marks = mark_elements(elements)

``propose_elements`` returns ``[{box, kind, index}]`` in reading order, where
``kind`` is ``text`` or ``widget``. It is the missing top-of-funnel for the
agent stack on un-modelled UIs: pixels in, a clean numbered element list out,
ready for marking, observation or grounding. Tune ``min_area`` for the smallest
control you care about and ``iou_threshold`` for how aggressively overlapping
text and widget boxes are merged.

Executor commands
-----------------

``AC_propose_elements`` (``region`` ``[x, y, w, h]`` / ``min_area`` /
``iou_threshold`` → ``{elements}``) runs the full pipeline on the screen, and
``AC_tag_kinds`` (``elements`` JSON list → ``{elements}``, pure) labels a
pre-fused list. They are the matching read-only ``ac_*`` MCP tools and Script
Builder commands under **Image**.
