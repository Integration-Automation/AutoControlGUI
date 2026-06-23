Action-Effect Classification (Did My Click Do Anything?)
========================================================

After an agent clicks, the crucial question is "did that do anything, and was it the *right*
thing?" — but nothing answered it on the *first* step. ``screen_state.diff_snapshots`` and
``element_diff`` report what changed but never tie the change back to the action;
``loop_guard`` only flags a no-op after the same digest repeats N times (so the agent loops
2–8 times first); ``actionability`` is purely a *pre*-action gate. ``action_effect`` closes the
loop: it diffs the before/after observation and, given the action's target point, classifies
the result so an agent can react immediately.

The verdict is one of ``no_op`` (nothing changed), ``changed_near_target`` (the change happened
where we acted — a button depressed), ``changed_elsewhere`` (a surprise dialog popped somewhere
else), or ``changed`` (something changed but the action carried no point to attribute to).

Pure-stdlib over element dicts + the action record; reuses ``element_diff.match_elements`` for
the overlap join and ``observation_delta``'s field-change check. Fully deterministic and
unit-testable with no device. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import classify_effect, effect_near_point, is_no_op

    verdict = classify_effect(before_elements, after_elements,
                              {"type": "click", "x": 480, "y": 260})
    if verdict.effect == "no_op":
        retry_or_repair()
    elif verdict.effect == "changed_elsewhere":
        handle_unexpected_dialog()

    if is_no_op(before_elements, after_elements):
        ...

``classify_effect`` returns an ``EffectVerdict`` (``effect`` / ``changed_near_target`` /
``changed_count`` / ``changed_centers`` / ``reason``). ``effect_near_point`` answers whether any
change landed within ``radius`` of an arbitrary point; ``is_no_op`` is the boolean shortcut.

Executor commands
-----------------

``AC_classify_effect`` (``before`` / ``after`` / ``action`` / ``radius`` →
``{effect, changed_near_target, changed_count, changed_centers, reason}``) and
``AC_effect_near_point`` (``before`` / ``after`` / ``point`` / ``radius`` → ``{near}``). They
are exposed as the MCP tools ``ac_classify_effect`` / ``ac_effect_near_point`` (read-only) and
as the Script Builder commands **Classify Action Effect** / **Effect Near Point?** under
**Native UI**.
