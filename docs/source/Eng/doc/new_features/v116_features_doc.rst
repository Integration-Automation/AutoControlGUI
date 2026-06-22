Multi-Waypoint Mouse Gestures
=============================

``humanize.humanized_path`` and ``tween_drag`` only interpolate a *single*
start → end hop. Real gestures — signatures, marquee / rubber-band selections,
dragging through several drop targets, shape gestures — need an arbitrary chain
of waypoints, with the button optionally held down across the whole path.

:func:`plan_path` is pure point math (reusing the named easings from
``tween_drag``) and is unit-testable on its own; :func:`move_along_path` and
:func:`drag_path` dispatch through an injectable ``sink`` so the gesture is
tested without real input. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        plan_path, move_along_path, drag_path, path_easings,
    )

    # the eased point list through every waypoint (junctions de-duplicated)
    plan_path([(100, 100), (400, 150), (400, 500)], per_segment_steps=20)

    move_along_path([(100, 100), (400, 150), (400, 500)])      # hover a polyline
    drag_path([(50, 50), (300, 50), (300, 300)], button="mouse_left")  # L-drag

``plan_path`` interpolates each consecutive pair with ``per_segment_steps`` eased
steps (``easing`` is any name from ``path_easings()`` — ``linear`` /
``ease_in_out_quad`` / ``ease_out_cubic`` / ``ease_in_cubic``) and does not
duplicate the shared junction points. ``move_along_path`` emits move events
through the path; ``drag_path`` presses at the first waypoint, moves through the
whole path, and releases at the last — for multi-stop drags. Both take a ``sink``
override for headless testing.

Executor commands
-----------------

``AC_move_along_path`` and ``AC_drag_path`` take ``waypoints`` (a JSON
``[[x, y], ...]`` list) plus ``easing`` / ``per_segment_steps`` (and ``button``
for the drag). Both are exposed as MCP tools (``ac_move_along_path`` /
``ac_drag_path``) and as Script Builder commands under **Mouse**.
