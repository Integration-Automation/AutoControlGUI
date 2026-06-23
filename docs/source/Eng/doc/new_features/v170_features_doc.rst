Repair-Tactic Policy for Failed / No-Effect Actions
===================================================

When an action does nothing or lands wrong, the agent needs a *policy* for what to try next —
re-locate and retry, nudge the coordinate, scroll the target into view, wait and retry, or give
up and escalate. ``self_healing`` / ``locator_repair`` only repair a locator that *did not
resolve* (element not found); they do nothing when the element was found and clicked but had no
effect. ``loop_guard`` only *detects* a stuck loop — it has no tactic selection or backoff.
``step_repair`` is that missing controller: it consumes an effect verdict (e.g. from
``action_effect``) and drives a bounded retry loop, choosing the next untried tactic each round.

Pure-stdlib state machine; every side effect — performing the action, verifying it, applying a
tactic, sleeping — is an injected callable, so the loop is fully deterministic and
unit-testable with no device. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (plan_repair, run_with_repair, RepairPolicy,
                                 classify_effect)

    # just the plan
    plan_repair("no_op")              # ['wait_retry', 'relocate', 'nudge']
    plan_repair("changed_elsewhere")  # ['escalate']

    # drive the loop with injected seams
    outcome = run_with_repair(
        act=lambda: click(*target),
        verify=lambda: not is_no_op(before(), after()),
        apply_tactic=apply,                 # e.g. relocate / nudge the target
        verdict_for=lambda: classify_effect(before(), after(), action).effect,
        policy=RepairPolicy(max_attempts=3))
    print(outcome.ok, outcome.tactics_used)

``plan_repair`` returns the ordered tactics for a verdict (a string like ``no_op`` /
``changed_elsewhere`` or an ``EffectVerdict`` dict), capped at ``max_attempts``;
``next_tactic`` returns the next untried one. ``run_with_repair`` runs ``act`` then ``verify``;
on failure it applies tactics until success or exhaustion, returning a ``RepairOutcome``
(``ok`` / ``attempts`` / ``tactics_used`` / ``detail``). ``RepairPolicy`` caps attempts and
lists the allowed tactics.

Executor command
----------------

``AC_plan_repair`` (``verdict`` / ``max_attempts`` → ``{count, tactics}``) is exposed as the
MCP tool ``ac_plan_repair`` (read-only) and as the Script Builder command **Plan Repair
Tactics** under **Native UI**. (The live ``run_with_repair`` loop is driven from Python, since
it takes injected callables.)
