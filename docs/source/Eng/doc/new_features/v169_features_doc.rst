Declarative Action Postconditions
=================================

After an action an agent (or a replay harness) usually has a concrete expectation: "a dialog
saying 'Saved' should appear AND the Submit button should disable". ``expect_poll`` /
``assert_eventually`` poll a *single condition* but have no notion of an action-bound
*postcondition spec*, and they don't diff against a *before* baseline (so they cannot express
"a NEW dialog appeared" — only "a dialog exists"). ``trajectory_eval`` rubrics are
whole-trajectory, not per-step screen state. ``postcondition`` fills the gap: a small JSON spec
of clauses evaluated against the after-observation (optionally diffed against the
before-observation), returning a per-clause pass/fail report.

Clauses: ``appears`` / ``disappears`` (diffed against ``before``), ``enabled`` / ``disabled``,
``text_present`` / ``text_absent``, and ``count`` (``equals`` / ``min``). Pure-stdlib over
element dicts; the spec is plain JSON so it rides into action files / MCP / the scheduler.
Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import check_postcondition, compile_postcondition

    spec = {"appears": {"role": "dialog", "name": "Saved"},
            "disabled": {"name": "Submit"}}
    report = check_postcondition(after_elements, spec, before=before_elements)
    if not report.ok:
        print("failed clauses:", report.failed)

    # turn a spec into a predicate to drive expect_poll
    predicate = compile_postcondition({"text_present": "Saved"})

``check_postcondition`` returns a ``PostconditionReport`` (``ok`` / ``clauses`` —
``[{type, ok, detail}]`` — / ``failed``). ``appears`` succeeds only when the element is in
``after`` and *not* in ``before`` (a genuinely new element); ``disappears`` requires a
``before`` frame. ``compile_postcondition`` returns an ``after -> bool`` predicate for pairing
with ``expect_poll`` / ``assert_eventually``.

Executor command
----------------

``AC_check_postcondition`` (``after`` / ``spec`` / ``before`` →
``{ok, clauses, failed}``) is exposed as the MCP tool ``ac_check_postcondition`` (read-only)
and as the Script Builder command **Check Postcondition** under **Native UI**.
