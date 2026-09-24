"""Expand RFC 5545 (iCalendar) recurrence rules into concrete datetimes.

The scheduler's cron is interval-style 5-field only — it cannot express
"every 2nd Tuesday", "the last weekday of the month", or "every weekday for 10
occurrences". This adds an RRULE parser and occurrence expander for the common
subset above cron.

Supported rule parts: ``FREQ`` (DAILY/WEEKLY/MONTHLY/YEARLY), ``INTERVAL``,
``COUNT``, ``UNTIL``, ``BYDAY`` (incl. ordinals like ``2MO`` / ``-1FR``),
``BYMONTHDAY`` (incl. negatives), ``BYMONTH``, ``BYSETPOS`` and ``WKST``.
Time-level parts (BYHOUR/BYMINUTE/BYSECOND) and BYWEEKNO/BYYEARDAY are out of
scope and rejected, as is a rule with both ``COUNT`` and ``UNTIL``. The clock is
injectable so ``next_occurrence`` is deterministic.

Pure standard library (``datetime`` + ``calendar``); imports no ``PySide6``.
"""
import datetime as _dt
from calendar import monthrange
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException

_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
_FREQS = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}
_SUPPORTED_PARTS = frozenset({"FREQ", "INTERVAL", "COUNT", "UNTIL", "BYDAY",
                              "BYMONTHDAY", "BYMONTH", "BYSETPOS", "WKST"})

ByDay = Tuple[Optional[int], int]


_MAX_INTERVAL = 9999


@dataclass(frozen=True)
class Recurrence:  # pylint: disable=too-many-instance-attributes
    """A parsed RFC 5545 recurrence rule (supported subset).

    RFC 5545 RRULE has many independent parts; they are kept as flat fields to
    mirror the specification.
    """

    freq: str
    interval: int = 1
    count: Optional[int] = None
    until: Optional[_dt.datetime] = None
    by_day: Tuple[ByDay, ...] = ()
    by_month_day: Tuple[int, ...] = ()
    by_month: Tuple[int, ...] = ()
    by_set_pos: Tuple[int, ...] = ()
    wkst: int = 0


# --- parsing ---------------------------------------------------------------

def _parse_int(name: str, token: str) -> int:
    try:
        return int(token)
    except ValueError as error:
        raise AutoControlException(f"{name} must be an integer, got {token!r}") from error


def _parse_ints(value: str, name: str = "value", low: int = -366,
                high: int = 366) -> Tuple[int, ...]:
    """Comma-separated integers, each non-zero and within ``low..high``."""
    numbers = tuple(_parse_int(name, token) for token in value.split(",") if token.strip())
    for number in numbers:
        if number == 0 or not low <= number <= high:
            raise AutoControlException(f"{name} value {number} is out of range")
    return numbers


def _parse_byday(value: str) -> Tuple[ByDay, ...]:
    result: List[ByDay] = []
    for token in (t.strip().upper() for t in value.split(",") if t.strip()):
        weekday = token[-2:]
        if weekday not in _WEEKDAYS:
            raise AutoControlException(f"invalid BYDAY token {token!r}")
        prefix = token[:-2]
        ordinal = _parse_int("BYDAY ordinal", prefix) if prefix else None
        if ordinal is not None and (ordinal == 0 or not -53 <= ordinal <= 53):
            raise AutoControlException(f"invalid BYDAY ordinal in {token!r}")
        result.append((ordinal, _WEEKDAYS[weekday]))
    return tuple(result)


def _parse_until(value: str) -> _dt.datetime:
    text = value.strip()
    is_utc = text.endswith("Z")
    bare = text[:-1] if is_utc else text
    if "T" in bare:
        parsed = _dt.datetime.strptime(bare, "%Y%m%dT%H%M%S")
    else:
        # A date-only UNTIL bounds the whole day inclusively.
        parsed = _dt.datetime.strptime(bare, "%Y%m%d").replace(
            hour=23, minute=59, second=59)
    return parsed.replace(tzinfo=_dt.timezone.utc) if is_utc else parsed


def _parse_limits(parts: Dict[str, str]) -> Tuple[int, Optional[int]]:
    """Validated ``(INTERVAL, COUNT)`` of a rule's parts."""
    # INTERVAL=0 repeated the same date forever, and BYMONTH=13 or
    # BYMONTHDAY=40 could never match -- the expansion then ran until the
    # calendar overflowed.
    interval = _parse_int("INTERVAL", parts.get("INTERVAL", "1"))
    count = _parse_int("COUNT", parts["COUNT"]) if "COUNT" in parts else None
    if interval < 1 or (count is not None and count < 1):
        raise AutoControlException("INTERVAL and COUNT must be at least 1")
    if interval > _MAX_INTERVAL:
        # A huge INTERVAL overflowed timedelta / date arithmetic with an
        # OverflowError instead of a rule error.
        raise AutoControlException(f"INTERVAL must be at most {_MAX_INTERVAL}")
    return interval, count


def parse_rrule(text: str) -> Recurrence:
    """Parse an RRULE string (with or without the ``RRULE:`` prefix)."""
    body = text.strip()
    if body.upper().startswith("RRULE:"):
        body = body[6:]
    parts = {}
    for token in body.split(";"):
        if "=" in token:
            key, value = token.split("=", 1)
            parts[key.strip().upper()] = value.strip()
    # An unsupported part used to be dropped, so BYHOUR=9,17 fired once a day
    # and BYYEARDAY=100 fired on 1 January: a wrong schedule, silently.
    unsupported = sorted(set(parts) - _SUPPORTED_PARTS)
    if unsupported:
        raise AutoControlException(f"unsupported RRULE parts: {', '.join(unsupported)}")
    if "COUNT" in parts and "UNTIL" in parts:
        raise AutoControlException("COUNT and UNTIL must not both be given (RFC 5545 3.3.10)")
    freq = parts.get("FREQ", "").upper()
    if freq not in _FREQS:
        raise AutoControlException(f"unsupported or missing FREQ {freq!r}")
    interval, count = _parse_limits(parts)
    return Recurrence(
        freq=freq,
        interval=interval,
        count=count,
        until=_parse_until(parts["UNTIL"]) if "UNTIL" in parts else None,
        by_day=_parse_byday(parts.get("BYDAY", "")),
        by_month_day=_parse_ints(parts.get("BYMONTHDAY", ""), "BYMONTHDAY", -31, 31),
        by_month=_parse_ints(parts.get("BYMONTH", ""), "BYMONTH", 1, 12),
        by_set_pos=_parse_ints(parts.get("BYSETPOS", ""), "BYSETPOS"),
        wkst=_WEEKDAYS.get(parts.get("WKST", "MO").upper(), 0),
    )


# --- candidate selection ---------------------------------------------------

def _apply_time(day: _dt.date, dtstart: _dt.datetime) -> _dt.datetime:
    return _dt.datetime(day.year, day.month, day.day, dtstart.hour,
                        dtstart.minute, dtstart.second, tzinfo=dtstart.tzinfo)


def _month_dates(year: int, month: int) -> List[_dt.date]:
    return [_dt.date(year, month, d)
            for d in range(1, monthrange(year, month)[1] + 1)]


def _monthday_ok(day: _dt.date, by_month_day: Tuple[int, ...]) -> bool:
    total = monthrange(day.year, day.month)[1]
    for value in by_month_day:
        if value > 0 and day.day == value:
            return True
        if value < 0 and day.day == total + value + 1:
            return True
    return False


def _byday_ok(day: _dt.date, by_day: Tuple[ByDay, ...]) -> bool:
    total = monthrange(day.year, day.month)[1]
    pos = (day.day - 1) // 7 + 1
    neg = -((total - day.day) // 7 + 1)
    for ordinal, weekday in by_day:
        if day.weekday() == weekday and ordinal in (None, pos, neg):
            return True
    return False


def _setpos(items: List[_dt.date], by_set_pos: Tuple[int, ...]) -> List[_dt.date]:
    if not by_set_pos:
        return items
    picked = []
    for pos in by_set_pos:
        index = pos - 1 if pos > 0 else len(items) + pos
        if 0 <= index < len(items):
            picked.append(items[index])
    return sorted(set(picked))


def _in_month_match(day: _dt.date, rule: Recurrence, has_md: bool,
                    has_day: bool) -> bool:
    if has_md and has_day:
        return (_monthday_ok(day, rule.by_month_day)
                and _byday_ok(day, rule.by_day))
    if has_md:
        return _monthday_ok(day, rule.by_month_day)
    return _byday_ok(day, rule.by_day)


def _select_in_month(year: int, month: int, rule: Recurrence) -> List[_dt.date]:
    has_md, has_day = bool(rule.by_month_day), bool(rule.by_day)
    return [day for day in _month_dates(year, month)
            if _in_month_match(day, rule, has_md, has_day)]


def _monthly_dates(year: int, month: int, dtstart: _dt.datetime,
                   rule: Recurrence) -> List[_dt.date]:
    if rule.by_month and month not in rule.by_month:
        return []
    if rule.by_month_day or rule.by_day:
        chosen = _select_in_month(year, month, rule)
    else:
        chosen = [d for d in _month_dates(year, month) if d.day == dtstart.day]
    return _setpos(sorted(set(chosen)), rule.by_set_pos)


def _weekday_set(dtstart: _dt.datetime, rule: Recurrence) -> set:
    if rule.by_day:
        return {weekday for _, weekday in rule.by_day}
    return {dtstart.weekday()}


def _weekly_dates(week_start: _dt.date, dtstart: _dt.datetime,
                  rule: Recurrence) -> List[_dt.date]:
    weekdays = _weekday_set(dtstart, rule)
    days = [week_start + _dt.timedelta(days=offset) for offset in range(7)]
    chosen = [d for d in days if d.weekday() in weekdays]
    if rule.by_month:
        chosen = [d for d in chosen if d.month in rule.by_month]
    return _setpos(chosen, rule.by_set_pos)


def _daily_dates(day: _dt.date, rule: Recurrence) -> List[_dt.date]:
    if rule.by_month and day.month not in rule.by_month:
        return []
    if rule.by_month_day and not _monthday_ok(day, rule.by_month_day):
        return []
    if rule.by_day and day.weekday() not in {wd for _, wd in rule.by_day}:
        return []
    return [day]


def _safe_date(year: int, month: int, day: int) -> Optional[_dt.date]:
    if 1 <= day <= monthrange(year, month)[1]:
        return _dt.date(year, month, day)
    return None


def _yearly_dates(year: int, dtstart: _dt.datetime,
                  rule: Recurrence) -> List[_dt.date]:
    if not rule.by_month and rule.by_day and not rule.by_month_day:
        # BYDAY ordinals count within the year here: -1FR is the year's
        # last Friday, 20MO its 20th Monday.
        return _setpos(_select_in_year(year, rule.by_day), rule.by_set_pos)
    # Without BYMONTH, BYMONTHDAY / BYDAY apply to every month of the year;
    # restricting them to dtstart's month gave one date a year.
    return _setpos(sorted(set(_yearly_month_dates(year, dtstart, rule))), rule.by_set_pos)


def _yearly_month_dates(year: int, dtstart: _dt.datetime,
                        rule: Recurrence) -> List[_dt.date]:
    if rule.by_month_day or rule.by_day:
        return [day for month in (rule.by_month or range(1, 13))
                for day in _select_in_month(year, month, rule)]
    dates = (_safe_date(year, month, dtstart.day)
             for month in (rule.by_month or (dtstart.month,)))
    return [day for day in dates if day is not None]


def _select_in_year(year: int, by_day: Tuple[ByDay, ...]) -> List[_dt.date]:
    chosen: List[_dt.date] = []
    days = [_dt.date(year, 1, 1) + _dt.timedelta(days=offset)
            for offset in range(366 if monthrange(year, 2)[1] == 29 else 365)]
    for ordinal, weekday in by_day:
        matching = [day for day in days if day.weekday() == weekday]
        if ordinal is None:
            chosen.extend(matching)
        elif -len(matching) <= ordinal <= len(matching):
            chosen.append(matching[ordinal - 1 if ordinal > 0 else ordinal])
    return sorted(set(chosen))


# --- period series (bounded: _MAX_SCAN_YEARS past dtstart, never past 9999)

#: A rule that can never match (BYMONTH=2;BYMONTHDAY=30) used to scan until
#: the calendar overflowed and let OverflowError out of the executor.
_MAX_SCAN_YEARS = 400


def _scan_end(dtstart: _dt.datetime) -> int:
    return min(dtstart.year + _MAX_SCAN_YEARS, _dt.MAXYEAR - 1)

def _add_months(year: int, month: int, delta: int) -> Tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _daily_series(rule: Recurrence,
                  dtstart: _dt.datetime) -> Iterator[_dt.datetime]:
    cursor = dtstart.date()
    step = _dt.timedelta(days=rule.interval)
    while cursor.year <= _scan_end(dtstart):
        for day in _daily_dates(cursor, rule):
            yield _apply_time(day, dtstart)
        cursor += step


def _weekly_series(rule: Recurrence,
                   dtstart: _dt.datetime) -> Iterator[_dt.datetime]:
    offset = (dtstart.weekday() - rule.wkst) % 7
    cursor = dtstart.date() - _dt.timedelta(days=offset)
    step = _dt.timedelta(weeks=rule.interval)
    while cursor.year <= _scan_end(dtstart):
        for day in _weekly_dates(cursor, dtstart, rule):
            yield _apply_time(day, dtstart)
        cursor += step


def _monthly_series(rule: Recurrence,
                    dtstart: _dt.datetime) -> Iterator[_dt.datetime]:
    year, month = dtstart.year, dtstart.month
    while year <= _scan_end(dtstart):
        for day in _monthly_dates(year, month, dtstart, rule):
            yield _apply_time(day, dtstart)
        year, month = _add_months(year, month, rule.interval)


def _yearly_series(rule: Recurrence,
                   dtstart: _dt.datetime) -> Iterator[_dt.datetime]:
    year = dtstart.year
    while year <= _scan_end(dtstart):
        for day in _yearly_dates(year, dtstart, rule):
            yield _apply_time(day, dtstart)
        year += rule.interval


_SERIES = {
    "DAILY": _daily_series, "WEEKLY": _weekly_series,
    "MONTHLY": _monthly_series, "YEARLY": _yearly_series,
}


# --- public expansion ------------------------------------------------------

def _normalize_until(until: Optional[_dt.datetime],
                     dtstart: _dt.datetime) -> Optional[_dt.datetime]:
    if until is None:
        return None
    aware_start = dtstart.tzinfo is not None
    aware_until = until.tzinfo is not None
    if aware_start and not aware_until:
        return until.replace(tzinfo=dtstart.tzinfo)
    if not aware_start and aware_until:
        # A naive DTSTART is local time: convert a UTC UNTIL to it rather
        # than dropping the offset (20240103T050000Z is 13:00 at +0800).
        return until.astimezone().replace(tzinfo=None)
    return until


def _after_until(moment: _dt.datetime,
                 limit_until: Optional[_dt.datetime]) -> bool:
    return limit_until is not None and moment > limit_until


def occurrences(rule: Recurrence, dtstart: _dt.datetime, *,
                count: Optional[int] = None, until: Optional[_dt.datetime] = None,
                max_iter: int = 100000) -> Iterator[_dt.datetime]:
    """Yield occurrence datetimes for ``rule`` anchored at ``dtstart``."""
    limit_count = rule.count if count is None else count
    limit_until = _normalize_until(rule.until if until is None else until,
                                   dtstart)
    # count=0 used to yield one date before checking the limit.
    remaining = limit_count if limit_count is not None else max_iter
    for index, moment in enumerate(_SERIES[rule.freq](rule, dtstart)):
        if remaining < 1 or index >= max_iter or _after_until(moment, limit_until):
            return
        if moment >= dtstart:
            yield moment
            remaining -= 1


def next_occurrence(rule: Recurrence, dtstart: _dt.datetime, *,
                    now: Optional[_dt.datetime] = None) -> Optional[_dt.datetime]:
    """Return the first occurrence at or after ``now`` (or ``None``)."""
    moment = now if now is not None else _dt.datetime.now(dtstart.tzinfo)
    for occurrence in occurrences(rule, dtstart):
        if occurrence >= moment:
            return occurrence
    return None
