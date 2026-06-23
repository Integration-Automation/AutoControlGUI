Wait Until Gone (Blocking Vanish Waits)
=======================================

``wait_for_image`` / ``wait_for_text`` block until something *appears*, and the
``observer`` fires async callbacks on vanish — but there was no *blocking* "wait
until this spinner / toast / dialog **disappears** then continue" call for an
image or text. ``wait_until_window_closed`` covers windows only. This adds the
missing vanish waits to the ``smart_waits`` family.

The generic :func:`wait_until_gone` takes any predicate, so its loop is
headless-testable without a real screen; the image / text helpers build that
predicate from the locate functions. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        wait_until_gone, wait_until_image_gone, wait_until_text_gone,
    )

    # generic: wait until any predicate has been falsey
    wait_until_gone(lambda: spinner_is_visible(), timeout_s=15)

    wait_until_image_gone("spinner.png", timeout_s=15)     # image left the screen
    wait_until_text_gone("Loading...", timeout_s=15)        # OCR text disappeared

Each returns a ``WaitOutcome`` (``succeeded`` / ``reason`` / ``elapsed_s`` /
``samples_taken``) — the same result type as the other smart waits. ``gone_for_s``
requires the target to stay absent for that long before succeeding (debounces a
flickering element); ``poll_interval_s`` / ``timeout_s`` bound the loop.

Executor commands
-----------------

``AC_wait_image_gone`` and ``AC_wait_text_gone`` take the target plus
``timeout_s`` / ``poll_interval_s`` / ``gone_for_s`` (and ``detect_threshold`` for
the image) and return the ``WaitOutcome`` dict. Both are exposed as MCP tools
(``ac_wait_image_gone`` / ``ac_wait_text_gone``) and as Script Builder commands
under **Flow**.
