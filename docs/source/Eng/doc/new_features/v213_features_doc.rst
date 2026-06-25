Wait Until the App Is Idle
==========================

A click fired while the app is still churning — the busy / wait cursor is up, a
dialog is mid-paint, a long handler is running — is dropped or mis-targeted.
``smart_waits`` watches *pixels* settling; ``app_idle`` watches the app's *busy
signal* settle instead, which is cheaper and survives animated-but-idle UI. It
reuses :class:`settle_detector.SettleTracker`: each poll feeds ``1.0`` when busy
and ``0.0`` when idle, and the wait returns once the app has read idle for
``quiet_samples`` polls in a row (a fresh busy spike resets the run).

* :func:`wait_until_app_idle` — poll a ``busy_probe`` until the app settles idle
  or a timeout, with injectable ``clock`` / ``sleep`` / ``busy_probe``.
* :func:`idle_point` — pure: the index in a recorded busy/idle sample series at
  which it first becomes settled-idle.

The default probe reports the Windows busy / app-starting cursor; every wait and
settle decision runs through the injectable seam, so it is fully testable
without an app. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import wait_until_app_idle, idle_point

    # Launch something, then wait for its busy cursor to settle before clicking
    start_exe("setup.exe")
    if wait_until_app_idle(quiet_samples=3, timeout_s=30)["idle"]:
        click_next()

    # Pure: analyse a recorded busy/idle trace
    idle_point([True, True, False, False, False], quiet_samples=3)   # 4

``wait_until_app_idle`` returns ``{idle, polls, quiet_run, elapsed_s}``. Pass a
custom ``busy_probe`` (a ``() -> bool``) to gate on any busy signal — a spinner
image match, a process-CPU threshold, an accessibility "busy" flag — not just the
cursor.

Executor commands
-----------------

``AC_wait_until_app_idle`` (``quiet_samples`` / ``timeout`` / ``interval`` →
``{idle, polls, quiet_run, elapsed_s}``, using the Windows busy cursor) and
``AC_idle_point`` (``busy_samples`` JSON list + ``quiet_samples`` → ``{index}``,
pure). They are the matching read-only ``ac_*`` MCP tools and Script Builder
commands under **Flow**.
