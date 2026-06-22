Calendar Recurrence Rules (RRULE)
=================================

The scheduler's cron is interval-style 5-field only — it cannot express "every
2nd Tuesday", "the last weekday of the month", or "every weekday for 10
occurrences". This adds an RFC 5545 (iCalendar) **RRULE** parser and occurrence
expander, the calendar layer above cron.

Supported rule parts: ``FREQ`` (DAILY/WEEKLY/MONTHLY/YEARLY), ``INTERVAL``,
``COUNT``, ``UNTIL``, ``BYDAY`` (incl. ordinals like ``2MO`` / ``-1FR``),
``BYMONTHDAY`` (incl. negatives), ``BYMONTH``, ``BYSETPOS`` and ``WKST``.
Time-level parts and BYWEEKNO/BYYEARDAY are out of scope. Pure standard library
(``datetime`` + ``calendar``); the clock is injectable so ``next_occurrence`` is
deterministic. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    import datetime
    from je_auto_control import parse_rrule, occurrences, next_occurrence

    rule = parse_rrule("FREQ=MONTHLY;BYDAY=2TU")     # every 2nd Tuesday
    start = datetime.datetime(2026, 1, 1, 9, 0)

    for moment in occurrences(rule, start, count=3):
        print(moment)            # 2026-01-13 09:00, 2026-02-10 09:00, ...

    # "last weekday of the month"
    last = parse_rrule("FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1")

    # next fire at or after a given time (inject now for determinism)
    nxt = next_occurrence(rule, start, now=datetime.datetime(2026, 3, 15))

``parse_rrule`` accepts the rule with or without the ``RRULE:`` prefix and
returns a frozen ``Recurrence``. ``occurrences`` yields datetimes anchored at
``dtstart`` (its time-of-day and timezone are applied to every occurrence),
bounded by ``COUNT`` / ``UNTIL`` (or the ``count=`` / ``until=`` overrides) and
a safety cap. A date-only ``UNTIL`` bounds the whole day inclusively.
``next_occurrence`` returns the first occurrence at or after ``now``.

Executor commands
-----------------

``AC_rrule_occurrences`` takes ``rule`` and an ISO ``dtstart`` (plus optional
``count``) and returns ``{occurrences}`` as ISO datetimes. ``AC_rrule_next``
takes ``rule`` / ``dtstart`` / optional ``now`` and returns ``{next}``. Both are
exposed as MCP tools (``ac_rrule_occurrences`` / ``ac_rrule_next``) and as
Script Builder commands under **Flow**.
