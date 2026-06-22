Multi-Monitor / Virtual-Desktop Geometry
========================================

``snap_window``, ``arrange_grid`` and the layout planner all take a single primary
``(width, height)`` — they are monitor-blind: they cannot tile on the second display
or cope with a negative-origin virtual desktop, and ``coordinate_space`` only rescales
a model grid. This adds the missing physical layer: enumerate the monitors, compute
the union virtual bounds, ask which monitor contains a point or a window, convert
between virtual and per-monitor-local coordinates, and remap a point to the equivalent
spot on another display.

The geometry is pure arithmetic over plain ``Monitor`` dataclasses, so it is fully
unit-testable; only ``enumerate_monitors``' default provider touches the OS (via
``mss``) and it is injectable. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (enumerate_monitors, monitor_at_point,
                                 virtual_bounds, to_local, remap_point)

    monitors = enumerate_monitors()
    print(virtual_bounds(monitors))            # (x, y, w, h) spanning all displays

    here = monitor_at_point(monitors, x, y)    # which monitor owns this point
    idx, lx, ly = to_local(monitors, x, y)     # virtual -> (monitor, local x, local y)

    # Move a point to the equivalent relative spot on another monitor.
    second = remap_point(monitors[0], monitors[1], 960, 540)

``Monitor`` carries ``index, x, y, width, height, scale, primary`` and a ``work``
area (``.bounds`` / ``.contains(x, y)`` / ``.to_dict()``). ``virtual_bounds`` returns
the union box (origin may be negative); ``primary_monitor`` picks the primary;
``monitor_for_window(rect, monitors)`` returns the display a window mostly occupies
(max overlap); ``to_virtual`` is the inverse of ``to_local``; ``remap_point``
preserves the fractional position so it works across differing resolutions and DPI.

Executor commands
-----------------

``AC_enumerate_monitors`` → ``{count, monitors, virtual_bounds}`` and
``AC_monitor_at_point`` (``x`` / ``y``) → ``{found, monitor}``. They are exposed as
the MCP tools ``ac_enumerate_monitors`` / ``ac_monitor_at_point`` and as Script
Builder commands under **Window**.
