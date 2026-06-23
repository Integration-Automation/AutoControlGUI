Line / Grid / Separator Detection (Hough)
=========================================

``grid_locator`` clusters *already-found* element boxes into a grid; it cannot find
the ruling lines of a table / spreadsheet or a UI divider from raw pixels, and
``shape_locator`` only finds closed rectangles. ``find_lines``, ``find_grid`` and
``find_separators`` detect straight line segments via Canny + the probabilistic Hough
transform, classify them horizontal / vertical / diagonal, recover a table's row and
column coordinates (and cells), and return the positions of long divider lines — so a
script can address "row 3, column 2" or split a panel at its separators with no
template.

Runs on an injectable ``haystack`` (ndarray / path / PIL), so it is headless-testable
on synthetic arrays. ``cv2.HoughLinesP`` is base OpenCV; OpenCV + NumPy come in via
``je_open_cv``. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import find_lines, find_grid, find_separators

    for seg in find_lines(min_length=80, orientation="vertical"):
        print(seg["x1"], seg["y1"], seg["x2"], seg["y2"], seg["length"])

    grid = find_grid(min_length=120)
    cell = grid["cells"][0]                     # {x, y, width, height} of row 0, col 0
    click(cell["x"] + cell["width"] // 2, cell["y"] + cell["height"] // 2)

    dividers = find_separators(axis="horizontal")   # [y0, y1, ...] of the rules

``find_lines`` returns ``{x1, y1, x2, y2, angle, length, orientation}`` per segment,
longest first; pass ``orientation`` other than ``any`` to keep only that kind.
``find_grid`` clusters the horizontal rules into row coordinates and the vertical rules
into columns, returning ``{rows, cols, cells}`` (cells are the rectangles between
consecutive rules). ``find_separators`` returns the merged coordinates of long divider
lines along ``axis``. A blank screen yields no lines / cells.

Executor commands
-----------------

``AC_find_lines`` (``min_length`` / ``max_gap`` / ``orientation`` / ``region`` →
``{count, lines}``), ``AC_find_grid`` (``min_length`` / ``tol`` / ``region`` →
``{rows, cols, cells}``) and ``AC_find_separators`` (``axis`` / ``min_length`` /
``tol`` / ``region`` → ``{count, axis, coordinates}``). They are exposed as the MCP
tools ``ac_find_lines`` / ``ac_find_grid`` / ``ac_find_separators`` and as Script
Builder commands under **Image**.
