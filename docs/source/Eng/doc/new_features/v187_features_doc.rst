Drop Files onto a Window (WM_DROPFILES)
=======================================

``clipboard_files`` *stages* a file-drop list on the clipboard so a user can
``Ctrl+V`` it; ``file_drop`` actively **drops** files onto a target window — the
completion of a drag-and-drop — by posting a ``WM_DROPFILES`` message carrying a
``DROPFILES`` blob. It reuses ``clipboard_files.build_dropfiles`` to pack that
blob (the byte layout is shared, not re-implemented) and dispatches it through an
injectable *driver* seam, so the build-and-dispatch logic is unit-testable on any
platform with a fake driver; the real ``GlobalAlloc`` + ``PostMessage`` lives in
the default Win32 driver. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import plan_file_drop, drop_files

    # Pure dry-run — inspect the payload without sending:
    plan_file_drop(["C:\\a\\one.txt"], point=(10, 20))
    # {"message": 0x233, "paths": [...], "point": [10, 20], "wide": True,
    #  "blob_size": ...}

    # Real drop onto a window handle (Windows):
    drop_files(hwnd, ["C:\\a\\one.txt", "C:\\b\\two.png"], point=(10, 20))

    # Inject a driver to intercept the send (e.g. in tests):
    drop_files(hwnd, ["x.txt"], driver=lambda hwnd, blob, point: True)

``point`` is the drop coordinate in the window's client area. ``drop_files``
returns ``bool``; the default driver posts the real ``WM_DROPFILES`` (the
receiving window then owns and frees the memory via ``DragFinish``) and raises
``RuntimeError`` off Windows.

Executor commands
-----------------

``AC_drop_files`` (``hwnd`` / ``paths`` / ``point``) performs the drop;
``AC_plan_file_drop`` (``paths`` / ``point``) is the pure dry-run. They are
exposed as the matching ``ac_*`` MCP tools (drop side-effect-only, plan
read-only) and as Script Builder commands under **Window**.
