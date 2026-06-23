Geometry-Aware Element Diff & Stable IDs
========================================

``screen_state.diff_snapshots`` keys element identity strictly on ``(role, name)`` — so
it cannot match an element whose label changed but position is stable, cannot track a
renamed control, and cannot produce persistent IDs across frames. Geometry-aware
matching (intersection-over-union, reusing :doc:`v138_features_doc`'s ``iou``) is the
basis for stable element IDs an agent can refer to turn-over-turn: a button that moved
a few pixels keeps its id, a renamed-but-stationary control matches by overlap, a
genuinely new element gets a fresh id.

Pure-stdlib over plain element dicts (``x`` / ``y`` / ``width`` / ``height``), so it is
fully unit-testable. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import match_elements, assign_stable_ids

    diff = match_elements(before_boxes, after_boxes, iou_threshold=0.5)
    for pair in diff["matched"]:
        print("moved/kept:", pair["before"], "->", pair["after"], pair["iou"])
    print("appeared:", diff["added"], "disappeared:", diff["removed"])

    # Carry stable IDs across frames so the agent can say "click element 7" reliably.
    frame1 = assign_stable_ids(boxes1)
    frame2 = assign_stable_ids(boxes2, prior=frame1)

``match_elements`` greedily pairs ``before`` ↔ ``after`` by overlap, returning
``{matched: [{before, after, iou}], added, removed}``. ``assign_stable_ids`` tags each
element with an ``id``; with a ``prior`` frame each element inherits the id of the
prior box it most overlaps (above ``iou_threshold``), and unmatched elements get fresh
ids beyond the highest prior id.

Executor commands
-----------------

``AC_match_elements`` (``before`` / ``after`` / ``iou_threshold`` → ``{matched, added,
removed}``) and ``AC_assign_stable_ids`` (``elements`` / ``prior`` / ``iou_threshold``
→ ``{count, elements}``). They are exposed as the MCP tools ``ac_match_elements`` /
``ac_assign_stable_ids`` and as Script Builder commands under **Native UI**.
