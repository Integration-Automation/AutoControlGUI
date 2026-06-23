Window Client-Area Geometry
===========================

``window_capture.get_window_geometry`` returns a window's *outer* bounding box (for
screenshotting), but there is no *client*-area rect, no frame-inset math, and no
client→screen point mapping. RPA needs "click at ``(x, y)`` *inside* this window's
client area regardless of title-bar height / borders" — the building block for
window-relative clicking. This adds the client rect, the pure frame-inset and
client-to-screen helpers, and a one-call ``client_point``.

``frame_insets`` / ``client_to_screen`` are pure geometry (headless-testable); only
``get_client_rect``'s default reader touches Win32 (``GetClientRect`` +
``ClientToScreen``), and it is injectable. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (get_client_rect, client_point, frame_insets,
                                 client_to_screen)

    # Click 20px in, 30px down from the window's content origin (not its title bar).
    point = client_point("Calculator", 20, 30)
    if point:
        click(*point)

    rect = get_client_rect("Calculator")               # (x, y, width, height)
    insets = frame_insets(get_window_geometry("Calculator"), rect)  # border sizes

``get_client_rect`` returns the client area as ``(x, y, width, height)`` with a
screen-coordinate origin (or ``None``); ``client_point`` maps a client-local point to
the screen so a click lands inside the content regardless of chrome. ``frame_insets``
returns the ``{left, top, right, bottom}`` border/title-bar thickness from the outer
and client rects, and ``client_to_screen`` is the underlying pure offset.

Executor commands
-----------------

``AC_get_client_rect`` (``title`` → ``{found, rect}``) and ``AC_client_point``
(``title`` / ``x`` / ``y`` → ``{found, point}``). They are exposed as the MCP tools
``ac_get_client_rect`` / ``ac_client_point`` and as Script Builder commands under
**Window**.
