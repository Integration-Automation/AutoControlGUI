"""Minimal cron-expression parser (5-field: minute hour dom month dow).

Supports ``*``, comma-lists (``1,5,10``), step values (``*/5``, ``5/15``)
and ranges (``1-4``). Enough for scheduling most automation jobs without
pulling in ``croniter`` as a dependency, and it follows the same rules:

* ``dow``: 0=Sun … 6=Sat, and 7 is Sunday too.
* When both day-of-month and day-of-week are restricted, a day matches if
  *either* does (``0 0 1 * 1`` is "the 1st, and every Monday").
* ``a/n`` means ``a-max/n`` (``5/15`` in minutes is 5, 20, 35, 50).
"""
import datetime as _dt
from dataclasses import dataclass
from typing import List, Set


_FIELD_BOUNDS = (
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 7),    # day of week (0=Sun, 7=Sun)
)


@dataclass(frozen=True)
class CronExpression:
    """Parsed five-field cron expression.

    Each slot is the set of allowed integers for that field.
    """
    minutes: Set[int]
    hours: Set[int]
    days_of_month: Set[int]
    months: Set[int]
    days_of_week: Set[int]
    #: Whether the field was written as ``*`` (or ``*/n``). Standard cron
    #: ORs the two day fields when *both* are restricted.
    dom_unrestricted: bool = True
    dow_unrestricted: bool = True

    def matches_day(self, day: _dt.date) -> bool:
        """Return ``True`` if ``day`` satisfies the month and day fields."""
        if day.month not in self.months:
            return False
        # Python weekday(): Mon=0..Sun=6 → cron dow: Sun=0..Sat=6
        dom_ok = day.day in self.days_of_month
        dow_ok = (day.weekday() + 1) % 7 in self.days_of_week
        if self.dom_unrestricted or self.dow_unrestricted:
            return dom_ok and dow_ok
        return dom_ok or dow_ok

    def matches(self, moment: _dt.datetime) -> bool:
        """Return ``True`` if ``moment`` satisfies every slot."""
        return (
            moment.minute in self.minutes
            and moment.hour in self.hours
            and self.matches_day(moment.date())
        )


def parse_cron(expression: str) -> CronExpression:
    """Parse a five-field cron expression; raise ``ValueError`` on failure."""
    fields = expression.strip().split()
    if len(fields) != 5:
        raise ValueError(
            f"cron expression must have 5 fields; got {len(fields)}: {expression!r}"
        )
    slots = [
        _parse_field(fields[i], _FIELD_BOUNDS[i][0], _FIELD_BOUNDS[i][1])
        for i in range(5)
    ]
    days_of_week = {day % 7 for day in slots[4]}  # 7 is Sunday as well
    return CronExpression(
        minutes=slots[0], hours=slots[1], days_of_month=slots[2],
        months=slots[3], days_of_week=days_of_week,
        dom_unrestricted=fields[2].startswith("*"),
        dow_unrestricted=fields[4].startswith("*"),
    )


def next_match(expression: CronExpression,
               after: _dt.datetime) -> _dt.datetime:
    """Return the next ``datetime`` (minute-resolution) matching ``expression``.

    Walks day by day and only then minute by minute, over up to eight years:
    one year was too short for ``0 0 29 2 *`` (29 February) whenever the
    next leap day was further away, and the scheduler then re-fired the job
    on every tick. A search that finds nothing raises ``ValueError``.
    """
    start = (after + _dt.timedelta(minutes=1)).replace(second=0, microsecond=0)
    times = sorted((hour, minute) for hour in expression.hours
                   for minute in expression.minutes)
    day = start.date()
    for _ in range(_SEARCH_DAYS):
        if expression.matches_day(day):
            for hour, minute in times:
                candidate = _dt.datetime.combine(
                    day, _dt.time(hour, minute), tzinfo=after.tzinfo)
                if candidate >= start:
                    return candidate
        day += _dt.timedelta(days=1)
    raise ValueError("cron expression has no match within eight years")


#: How far ``next_match`` looks: eight years always contain a 29 February
#: (a leap day can be eight years from the last one around a century).
_SEARCH_DAYS = 8 * 366


def _parse_field(raw: str, lo: int, hi: int) -> Set[int]:
    values: Set[int] = set()
    for piece in raw.split(","):
        values.update(_expand_piece(piece, lo, hi))
    return values


def _expand_piece(piece: str, lo: int, hi: int) -> List[int]:
    step = 1
    if "/" in piece:
        base, step_str = piece.split("/", 1)
        step = int(step_str)
        if step <= 0:
            raise ValueError(f"cron step must be positive: {piece!r}")
    else:
        base = piece

    if base == "*":
        start, stop = lo, hi
    elif "-" in base:
        start_str, stop_str = base.split("-", 1)
        start, stop = int(start_str), int(stop_str)
    else:
        start = stop = int(base)
        if "/" in piece:
            stop = hi  # ``a/n`` is ``a-max/n``, as in Vixie cron and croniter

    if start < lo or stop > hi or start > stop:
        raise ValueError(
            f"cron field {piece!r} out of range [{lo}, {hi}]"
        )
    return list(range(start, stop + 1, step))
