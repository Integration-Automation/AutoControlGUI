Localize a Change to the Elements That Changed
==============================================

The existing diffs answer "*where* did pixels change" (``motion_regions``,
``perceptual_diff``, ``ssim_changed_regions`` return raw pixel regions) or "which
*accessibility* elements differ" (``element_diff``, needs a11y metadata). The
missing middle is: given a frame diff **and a list of element boxes**, which of
*those* elements changed? ``change_localize`` scores each supplied box by how
much it changed and ranks them.

* :func:`rank_changes` — pure: take ``[{box, score}]`` and mark each box
  ``changed`` (score at or above ``threshold``), sorted most-changed first.
* :func:`localize_changes` — diff a reference against the current screen, score
  each element box by its mean pixel change, and rank them.

``cv2`` / ``numpy`` are imported lazily (the module stays importable without
them) and the loaders reuse :mod:`visual_match`. The ranking is pure and fully
testable. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import localize_changes, rank_changes, mark_elements

    boxes = [mark["bbox"] for mark in mark_elements(elements)]

    # After an action, which of those elements actually changed?
    changed = localize_changes("before.png", boxes, current="after.png")
    for entry in changed:
        if entry["changed"]:
            print("element changed:", entry["box"], entry["score"])

    # Or rank pre-computed scores yourself:
    rank_changes([{"box": [0, 0, 40, 20], "score": 0.6}], threshold=0.1)

``localize_changes`` returns ``[{box, score, changed}]`` sorted most-changed
first, where ``score`` is the box's mean per-pixel change (0..1). It pairs with
``set_of_marks`` / accessibility element boxes to turn a raw screen diff into a
per-element "what changed" signal — an agent feedback channel after a click.

Executor commands
-----------------

``AC_localize_changes`` (``reference`` + ``boxes`` JSON list + ``current`` /
``threshold`` / ``region`` → ``{changes}``) and ``AC_rank_changes``
(``scored_boxes`` JSON list + ``threshold`` → ``{changes}``, pure). They are the
matching read-only ``ac_*`` MCP tools and Script Builder commands under
**Image**.
