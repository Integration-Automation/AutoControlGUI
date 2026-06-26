Trial and Force Action Modes (Playwright-style)
===============================================

``actionability.act_when_ready`` has one behaviour: wait for the target to be
actionable, then act (or raise on timeout). Real flows need two more modes that
Playwright codified:

* **trial** — run every actionability check but *don't* perform the action; just
  report whether it *would* have acted. The dry run for "is this control ready?"
  without side effects.
* **force** — skip the checks and act *now*, the deliberate escape hatch when the
  gate is wrong (a control the heuristics misjudge as occluded / disabled).

:func:`act_with_mode` adds both alongside the default gated (``auto``) behaviour,
over the same injectable seams as the gate, so each mode is testable without a
screen. Reuses :func:`actionability.wait_actionable`. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import act_with_mode

    bbox = lambda: (x, y, w, h)
    click = lambda point: do_click(point[0], point[1])

    act_with_mode(click, bbox, mode="auto")    # gate, then click if ready
    report = act_with_mode(click, bbox, mode="trial")  # dry run, never clicks
    if report["actionable"]:
        ...
    act_with_mode(click, bbox, mode="force")   # click now, no checks

Every mode returns ``{mode, acted, actionable, reason, point, result}``:
``acted`` says whether the action ran, ``actionable`` / ``reason`` come from the
gate (``trial`` reports these without acting), and ``result`` is the action's
return value. The actionability probes (``region_sampler`` / ``enabled_probe`` /
``hit_tester``) and ``config`` are forwarded to the gate as usual. An unknown
``mode`` raises ``ValueError``.

Executor commands
-----------------

``AC_act_with_mode`` (``x`` / ``y`` + ``mode`` / ``button`` → ``{mode, acted,
actionable, reason, point}``) clicks a point under the chosen mode — ``trial``
is a dry-run probe that never clicks, ``force`` clicks unconditionally. It is the
matching ``ac_act_with_mode`` MCP tool and a Script Builder command under
**Flow**. :func:`act_with_mode` (which takes an arbitrary action) is the
Python-API surface.
