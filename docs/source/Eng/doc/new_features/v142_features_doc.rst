Retrying Value Assertions (expect.poll)
=======================================

``assert_eventually`` can only poll the framework's fixed dict-spec dispatch table
(text / image / pixel / window / clipboard / process / file / http). It cannot retry an
*arbitrary* value — an OCR'd total equalling ``"$42.00"``, a row count stabilising, a
custom predicate. ``expect_poll`` takes any zero-argument ``getter`` and any
``matcher`` predicate and polls until it passes or the timeout elapses, with injectable
``clock`` / ``sleep`` so it is deterministic in tests (the existing helper calls real
``time.sleep``). It mirrors Playwright's ``expect.poll`` / web-first retrying assertions.

Pure-stdlib, imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (expect_poll, assert_poll, to_equal, to_contain,
                                 to_be_greater_than, to_match_regex, to_be_stable)

    # Poll an arbitrary getter until it matches.
    result = expect_poll(lambda: read_cart_total(), to_equal("$42.00"),
                         timeout_s=8.0, interval_s=0.5)
    if result.ok:
        print("settled after", result.attempts, "tries")

    # Raise on failure (assertion style).
    assert_poll(lambda: row_count(), to_be_greater_than(0))

    # Wait for a value to stop changing.
    expect_poll(lambda: ocr_value(), to_be_stable(3))

``expect_poll`` returns a ``PollResult`` (``ok``, ``value``, ``attempts``,
``waited_s``, ``description``); ``assert_poll`` raises ``AutoControlActionException``
when it never matches. The matcher factories are ``to_equal``, ``to_contain``,
``to_be_greater_than``, ``to_match_regex``, ``to_be_truthy`` and ``to_be_stable(n)``
(matches once the value repeats ``n`` times).

Executor command
----------------

``AC_expect_poll`` re-runs a nested ``action`` (e.g. ``["AC_get_clipboard"]``) until a
``key`` of its result matches ``op`` (``truthy`` / ``equals`` / ``contains`` / ``gt``
/ ``regex``) versus ``expected``, or ``timeout_s`` elapses — returning
``{ok, value, attempts, waited_s}``. It is exposed as the MCP tool ``ac_expect_poll``
and as a Script Builder command under **Flow**.
