=========================================================
New Features (2026-06-19) — Visual Regression & FSM
=========================================================

Two headless cores that already existed but were never wired through the
rest of the stack are now first-class: **golden-image visual regression**
and a **declarative finite-state-machine** runner. Both ship a facade
re-export, an ``AC_*`` executor command, an MCP tool, and a Script Builder
entry, with headless tests (PIL images / specs are injected, so nothing
needs a real screen).

.. contents::
   :local:
   :depth: 2


Visual regression (golden images)
=================================

Capture a baseline image and later fail a run when the screen drifts from
it — the screenshot equivalent of a snapshot test::

    from je_auto_control import take_golden, compare_to_golden

    take_golden("goldens/login.png")                      # establish baseline
    result = compare_to_golden("goldens/login.png", tolerance=0.5)
    if not result.matched:
        result.write_diff("goldens/login.diff.png")
        print(result.summary)

``compare_to_golden`` returns a ``DiffResult`` (``matched``, ``diff_pct``,
``differing_pixels``, a highlighted ``diff_image``); ``tolerance`` is the
percentage of pixels allowed to differ and ``per_pixel_threshold`` ignores
small per-channel noise. ``MaskRegion`` excludes animated / volatile areas.
PIL-only — no OpenCV / SciPy dependency.

Executor commands:

* ``AC_take_golden`` — capture and save a baseline (optional ``region``).
* ``AC_assert_visual`` — compare the screen to a golden and raise on
  mismatch (saving an optional ``diff_path``). On the **first run** (golden
  missing) it captures the baseline and passes, unless
  ``create_if_missing`` is false.


Finite-state machine
====================

Drive a script as a declarative state machine — clearer than nested
loops / ifs for screen-flow automation::

    from je_auto_control import run_state_machine

    spec = {
        "initial": "login",
        "states": {
            "login": {"on_enter": [["AC_click_text", {"text": "Sign in"}]],
                       "transitions": [{"go_to": "home", "after": 1.0}]},
            "home": {"final": True},
        },
    }
    result = run_state_machine(spec)   # {final_state, steps, elapsed_s}

Each state's ``on_enter`` actions run through the executor; transitions
fire on guards (``after`` a delay, ``if_var_eq``, or a caller predicate).
``max_steps`` and ``global_timeout_s`` bound the run so it can't loop
forever.

Executor command: ``AC_run_state_machine`` (the ``spec`` dict travels in
JSON action files / the socket server / MCP unchanged).
