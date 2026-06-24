Reactive UIA Event Wait — Focus Change
======================================

The accessibility recorder *polls* the focused element every ~250 ms, so it can
miss a fast focus transition and reacts a quarter-second late. UIA exposes real
events: ``wait_for_focus_change`` blocks on the native
``AddFocusChangedEventHandler`` and returns the moment focus moves — the
zero-latency, miss-free "wait until focus lands on the dialog" primitive, the
accessibility-tree analogue of ``wait_for_window`` / ``wait_for_image``.

It is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam — headless-testable on any platform by injecting a fake backend; the real
event subscription (registered / unregistered under a lock, on the calling
thread) lives in the Windows backend. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import wait_for_focus_change, click_text

    click_text("Settings")
    focused = wait_for_focus_change(timeout=3)
    # {"name": "Search", "role": "ControlType_50004", "app_name": "app.exe", ...}
    if focused is not None:
        ...   # focus has moved — the dialog / next field is ready

Returns the newly-focused element as ``{name, role, app_name, bounds, …}``, or
``None`` if no focus change occurs within ``timeout`` seconds (default ``5``).

Executor commands
-----------------

``AC_wait_for_focus_change`` (``timeout``) returns ``{changed, element}``. It is
exposed as the read-only ``ac_wait_for_focus_change`` MCP tool and as a Script
Builder command under **Native UI**.
