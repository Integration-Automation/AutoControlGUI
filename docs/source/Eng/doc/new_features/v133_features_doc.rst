Window Tiling / Layout Geometry Planner
=======================================

``save_window_layout`` / ``restore_window_layout`` capture and replay the *exact*
positions a user already arranged, and ``snap_window`` moves *one* window to a half
or quarter. Nothing *computes* a fresh multi-window layout. ``tile_rect``,
``grid_rects`` and ``cascade_rects`` are a pure-geometry planner: given a screen
work area they return the target rectangles for the common tiling layouts — halves,
quadrants, thirds, an R×C grid, a staggered cascade — so a script can lay out
application windows deterministically.

The planner is cross-platform and has no device dependency, so it is fully
unit-testable; the rectangles it returns compose with any window-move backend.
Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import tile_rect, grid_rects, cascade_rects

    left = tile_rect((0, 0, 1920, 1080), "left_third", gap=8)
    print(left.as_tuple())                  # (8, 8, 624, 1064)

    for cell in grid_rects((0, 0, 1920, 1080), rows=2, cols=3):
        window_move("Editor", *cell.as_tuple())   # 6-up grid

    plan = cascade_rects((0, 0, 1920, 1080), count=4, offset=40)

``tile_rect`` returns a ``WindowRect`` (``x, y, width, height`` with ``.as_tuple()``
and ``.to_dict()``) for a named ``slot`` — see :func:`available_slots`
(``left``, ``top_right``, ``center``, ``left_third`` …); ``gap`` insets all sides
for a margin between tiles. ``grid_rects`` returns one rectangle per cell of an
``rows`` × ``cols`` grid, row-major. ``cascade_rects`` returns ``count`` staggered,
overlapping rectangles clamped to the screen (``size`` defaults to 60% of the work
area). Unknown slots / non-positive grid dimensions raise ``ValueError``.

Executor commands
-----------------

``AC_tile_rect`` (``slot`` / ``screen`` / ``gap`` → ``{rect}``), ``AC_grid_rects``
(``rows`` / ``cols`` / ``screen`` / ``gap`` → ``{count, rects}``) and
``AC_cascade_rects`` (``count`` / ``screen`` / ``offset`` / ``size`` →
``{count, rects}``). ``screen`` defaults to the live primary screen work area. They
are exposed as the MCP tools ``ac_tile_rect`` / ``ac_grid_rects`` /
``ac_cascade_rects`` and as Script Builder commands under **Window**.
