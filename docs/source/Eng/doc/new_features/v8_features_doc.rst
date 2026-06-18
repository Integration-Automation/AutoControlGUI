=============================================
New Features (2026-06-19) — Popup Watchdog
=============================================

The #1 reason unattended automation fails is an unexpected dialog the
script was never coded for — a UAC prompt, a "session expiring" banner, a
Windows Update toast, a newsletter modal. The popup watchdog runs a
concurrent guard thread that watches for registered patterns and dismisses
them *independently* of the main step sequence, so a long run keeps going.

Surfaced by the practitioner pain-point research as the top unattended
failure cause. Ships through the full stack (facade, ``AC_*`` executor
commands, MCP tools, Script Builder) and is fully headless — matchers and
actions are injectable, so it's unit-tested without a real desktop.

.. contents::
   :local:
   :depth: 2


Quick start
===========

::

    from je_auto_control import default_popup_watchdog

    # Auto-close any window whose title contains "Update Available".
    default_popup_watchdog.add_window_rule("Update Available", action="close")
    # Press Esc on a "Session expiring" dialog instead of closing it.
    default_popup_watchdog.add_window_rule("Session expiring", action="esc")
    default_popup_watchdog.start()
    ...                                  # run your main flow
    default_popup_watchdog.stop()

``action`` is ``"close"`` (close the matching window) or a key name to
press (``"enter"`` / ``"esc"`` / ...). The guard polls on a background
thread and records every dismissal in ``default_popup_watchdog.hits``.


Custom rules
============

For non-window popups, register a generic rule pairing a *detector* with a
*dismisser*::

    from je_auto_control import PopupWatchdog, WatchdogRule

    watchdog = PopupWatchdog(poll_interval_s=0.5)
    watchdog.add_rule(WatchdogRule(
        name="cookie-banner",
        matcher=lambda: locate_image_center("cookie.png") is not None,
        action=lambda: click_text("Accept"),
    ))

A rule whose ``matcher``/``action`` raises is logged and skipped — one bad
rule never kills the guard loop.


Executor commands
=================

* ``AC_watchdog_add`` — register a window rule (``title`` + ``action``).
* ``AC_watchdog_start`` / ``AC_watchdog_stop`` — control the guard thread.
* ``AC_watchdog_list`` — report run state, rules, and dismissals.

A typical unattended script adds its rules and starts the watchdog before
the main work, so any stray dialog is cleared automatically.
