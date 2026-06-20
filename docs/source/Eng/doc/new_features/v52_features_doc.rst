Saga / Compensating Rollback
============================

Some automations span several irreversible-looking steps — create a record, send
an email, move a file. If a later step fails, the already-completed steps should
be **undone**, but the executor's ``AC_try`` only does try/catch/finally for one
block; nothing tracked "what to undo" across N completed steps. A ``Saga``
records a compensating action per step and, on any failure, runs the
compensations for the completed steps in **LIFO** order.

Forward actions and compensations are plain callables (or, via the executor, JSON
action lists), so the orchestration is fully unit-testable with no real side
effects. Compensation is best-effort: a failing compensation is logged and the
rollback continues. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import Saga

    result = (Saga()
              .step("create", create_record, delete_record)
              .step("notify", send_email, None)          # nothing to undo
              .step("move", move_file, restore_file)
              .run())

    if not result.ok:
        result.failed_step      # which step raised
        result.completed        # steps that ran forward
        result.compensated      # steps undone (LIFO over completed)

``run()`` returns a ``SagaResult`` (``ok`` / ``completed`` / ``compensated`` /
``failed_step`` / ``error``). A step "fails" when its action raises; steps with no
compensation are simply skipped during rollback.

Executor command
----------------

``AC_run_saga`` takes ``steps`` — a list (or JSON string) of ``{name, action:
[...], compensation: [...]}`` where each ``action`` / ``compensation`` is an
AutoControl action list. It returns ``{ok, completed, compensated, failed_step,
error}``. The same operation is exposed as the MCP tool ``ac_run_saga`` and as a
Script Builder command under **Flow**.
