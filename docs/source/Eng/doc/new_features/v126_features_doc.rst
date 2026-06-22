Wait for Window Title (Regex)
=============================

``wait_for_window`` matches a window title by *substring* and only waits for it to
*appear*; ``wait_until_window_closed`` is the substring vanish. Neither supports a
regular-expression title or "wait until the active window's title matches P" —
e.g. waiting for a browser tab to finish navigating to ``r".*— Checkout$"``. This
adds a regex title wait to the ``smart_waits`` family.

The title source is injectable, so the loop is headless-testable without real
windows. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import wait_until_window_title

    wait_until_window_title(r".*— Checkout$", timeout_s=20)   # tab navigated
    wait_until_window_title("Updating", present=False)         # dialog gone
    wait_until_window_title("Checkout", regex=False)           # substring mode

By default ``pattern`` is a regular expression (``re.search``); pass
``regex=False`` for a plain substring test. ``present=False`` waits for the title
to *vanish*. The result is a ``WaitOutcome`` (``succeeded`` / ``reason`` /
``elapsed_s`` / ``samples_taken``); ``title_lister`` is injectable for tests.

Executor commands
-----------------

``AC_wait_window_title`` takes ``pattern`` plus ``present`` / ``regex`` /
``timeout_s`` / ``poll_interval_s`` and returns the ``WaitOutcome`` dict. It is
exposed as the MCP tool ``ac_wait_window_title`` and as a Script Builder command
under **Flow**.
