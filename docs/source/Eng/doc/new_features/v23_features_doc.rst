==================================================
New Features (2026-06-19) — Semantic Screen State
==================================================

The *semantic* companion to the existing pixel (visual-regression) diff:
snapshot the accessibility tree, diff two snapshots into what **appeared /
vanished / moved**, and get a compact structured **description** of the
screen. This is the feedback signal an agent needs to verify a step's
effect and orient itself. Pure standard library; full stack.

.. contents::
   :local:
   :depth: 2


Snapshot & diff
==============

::

    from je_auto_control import snapshot, diff_snapshots, snapshot_screen, screen_changed

    before = snapshot_screen()      # baseline from the live a11y tree
    ...                              # perform a step
    delta = screen_changed()         # diff vs the baseline
    delta["summary"]                 # ["appeared: window Save", "moved: button OK"]

``snapshot`` normalizes elements to ``[{role, name, bbox}]`` (identity =
``(role, name)``); ``diff_snapshots(before, after)`` returns ``added`` /
``removed`` / ``moved`` lists plus a human-readable ``summary`` and
``changed_count``. ``snapshot_screen`` / ``screen_changed`` capture and diff
the *live* tree (caching the baseline). Exposed as ``AC_screen_snapshot`` /
``AC_screen_diff`` / ``AC_screen_changed``.


Describe the screen
==================

::

    from je_auto_control import describe_screen

    describe_screen()    # {app, element_count, by_role: {...}, controls: [...]}

A cheap "where am I" for an agent: counts per role and the labels of the
interactive controls. Exposed as ``AC_describe_screen`` /
``ac_describe_screen`` (and ``ac_screen_*`` for the diff family).
