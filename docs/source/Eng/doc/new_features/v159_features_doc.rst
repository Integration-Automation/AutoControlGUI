Coarse Labelled Screen Grid (VLM Grounding)
===========================================

Vision / VLM grounding works far better when a model can refer to a *coarse cell*
("click cell C3") than to raw pixel coordinates, which it tends to hallucinate — a
labelled overlay grid is the standard way to describe a screenshot to such a model and
to map its answer back to a point. The framework had no such helper. ``screen_grid``
lays an ``rows`` x ``cols`` grid over the screen (or a sub-``region``), labels each cell
spreadsheet-style (column letter + row number, ``A1`` top-left) and converts both ways.

Pure-stdlib geometry; the only device-bound path is the default that grabs the live
screen size when neither ``region`` nor ``screen_size`` is given, so every function is
fully unit-testable by passing an explicit region. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import grid_cells, cell_for_point, point_for_cell, click

    # describe the screen to a model as a 4x4 grid
    for cell in grid_cells(4, 4):
        print(cell.label, cell.center)

    # the model answers "C3" -> turn it into a click
    click(*point_for_cell("C3", 4, 4))

    # which cell did the user click in?
    cell = cell_for_point(820, 410, 4, 4)
    print(cell.label if cell else "outside")

``grid_cells(rows, cols, *, region=None, screen_size=None)`` returns row-major
``GridCell`` objects (``label`` / ``row`` / ``col`` / ``left`` / ``top`` / ``right`` /
``bottom`` + ``center``). ``cell_for_point`` returns the containing cell (or ``None`` if
the point is outside the region); ``point_for_cell`` returns the centre ``[x, y]`` of a
named cell, ready to click. Labels run past ``Z`` spreadsheet-style (``AA``, ``AB`` …).

Executor commands
-----------------

``AC_grid_cells`` (``rows`` / ``cols`` / ``region`` → ``{count, cells}``),
``AC_cell_for_point`` (``x`` / ``y`` / ``rows`` / ``cols`` / ``region`` →
``{found, cell}``) and ``AC_point_for_cell`` (``label`` / ``rows`` / ``cols`` /
``region`` → ``{point}``). They are exposed as the MCP tools ``ac_grid_cells`` /
``ac_cell_for_point`` / ``ac_point_for_cell`` (read-only) and as Script Builder
commands under **Image**.
