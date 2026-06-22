Arrange Multiple Windows (Grid / Cascade)
=========================================

``snap_window`` moves *one* window to a half or quarter, and the
:doc:`v133_features_doc` planner *computes* rectangles but does not move anything.
``arrange_grid`` and ``arrange_cascade`` close the loop: given a list of window
titles they compute a layout and actually move every matching window — tile a set
of app windows into a grid, or fan them out in a diagonal cascade, in one call.

They build on the layout planner for the geometry and reuse the same injectable
``mover`` / ``screen_size`` seams as ``snap_window``, so the arrangement logic is
fully unit-testable without real windows. The default mover is Win32 today (other
platforms are a no-op until their backend lands). Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import arrange_grid, arrange_cascade

    # Tile three editors into an auto-shaped grid (here 2x2, first 3 cells).
    arrange_grid(["Editor", "Browser", "Terminal"])

    # Or an explicit 1x3 row with an 8px gutter.
    arrange_grid(["Left", "Mid", "Right"], rows=1, cols=3, gap=8)

    # Fan windows out diagonally.
    arrange_cascade(["Doc 1", "Doc 2", "Doc 3"], offset=40)

``arrange_grid`` tiles the ``titles`` into an ``rows`` × ``cols`` grid (defaulting
to a near-square auto-shape for the window count) with an optional ``gap``;
``arrange_cascade`` staggers each window ``offset`` pixels down-right of the
previous, sized to 60% of the work area. Both return the number of windows
actually moved and leave any windows beyond the grid capacity untouched.

Executor commands
-----------------

``AC_arrange_grid`` (``titles`` JSON array + ``rows`` / ``cols`` / ``gap``) and
``AC_arrange_cascade`` (``titles`` + ``offset``), each returning
``{moved, count}``. They are exposed as the MCP tools ``ac_arrange_grid`` /
``ac_arrange_cascade`` (side-effecting) and as Script Builder commands under
**Window**.
