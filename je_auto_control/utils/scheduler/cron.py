"""Minimal cron-expression parser (5-field: minute hour dom month dow).

Supports ``*``, comma-lists (``1,5,10``), step values (``*/5``) and ranges
(``1-4``). Enough for scheduling most automation jobs without pulling in
``croniter`` as a dependency.

``dow``: 0=Sun, 6=Sat to match standard cron.
"""
import datetime as _dt
from dataclasses import dataclass
from typing import List, Set


_FIELD_BOUNDS = (
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 6),    # day of week (0=Sun)
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

    def matches(self, moment: _dt.datetime) -> bool:
        """Return ``True`` if ``moment`` satisfies every slot."""
        # Python weekday(): Mon=0..Sun=6 → cron dow: Sun=0..Sat=6
        cron_dow = (moment.weekday() + 1) % 7
        return (
            moment.minute in self.minutes
            and moment.hour in self.hours
            and moment.day in self.days_of_month
            and moment.month in self.months
            and cron_dow in self.days_of_week
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
    return CronExpression(
        minutes=slots[0], hours=slots[1], days_of_month=slots[2],
        months=slots[3], days_of_week=slots[4],
    )


def next_match(expression: CronExpression,
               after: _dt.datetime) -> _dt.datetime:
    """Return the next ``datetime`` (minute-resolution) matching ``expression``.

    Searches up to one year ahead to keep the runtime bounded.
    """
    moment = (after + _dt.timedelta(minutes=1)).replace(second=0, microsecond=0)
    limit = moment + _dt.timedelta(days=366)
    while moment < limit:
        if expression.matches(moment):
            return moment
        moment += _dt.timedelta(minutes=1)
    raise ValueError("cron expression has no match within 366 days")


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

    if start < lo or stop > hi or start > stop:
        raise ValueError(
            f"cron field {piece!r} out of range [{lo}, {hi}]"
        )
    return list(range(start, stop + 1, step))
