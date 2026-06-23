Soft Assertions — Aggregate Failures at Block End
=================================================

``assertion.assert_all`` takes a **pre-built list of spec dicts up front**. There is no
*scoped accumulator* you sprinkle ``check()`` calls into across interleaved actions and
that raises everything at once on exit — the JUnit5 ``assertAll`` / Playwright
``expect.soft`` / AssertJ ``SoftAssertions`` pattern, the standard ergonomics for
verifying many fields of a form without stopping at the first failure.

Pure-stdlib context manager; imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import SoftAssertions

    with SoftAssertions() as soft:
        soft.check(title == "Invoice", "wrong title")
        soft.check_equal(total, "$42.00", "wrong total")
        soft.check(date_field_is_visible(), "date field missing")
    # on exit, raises once listing EVERY failed check (or nothing if all passed)

``check(condition, message)`` records a pass/fail and never raises (it returns the
bool, so you can branch on it); ``check_equal(actual, expected, message)`` is the
equality shortcut. ``failures`` lists the failed messages, ``passed`` counts the
passes, and ``assert_all()`` raises ``AutoControlActionException`` aggregating them.
The context manager calls ``assert_all`` on a clean exit (and never masks an exception
already propagating). Pass ``raise_on_exit=False`` to collect without auto-raising.

Executor command
----------------

``AC_soft_assert`` evaluates a list of ``checks`` (each ``{value, op, expected,
message}`` with ``op`` = ``eq`` / ``ne`` / ``gt`` / ``lt`` / ``contains`` /
``truthy``) and returns ``{ok, passed, failures}`` — reporting *all* failures, not
just the first; set ``raise_on_fail`` to raise instead. It is exposed as the MCP tool
``ac_soft_assert`` and as a Script Builder command under **Flow**.
