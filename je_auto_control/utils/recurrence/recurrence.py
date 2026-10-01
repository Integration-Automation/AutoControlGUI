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
    try:
        if "T" in bare:
            parsed = _dt.datetime.strptime(bare, "%Y%m%dT%H%M%S")
        else:
            # A date-only UNTIL bounds the whole day inclusively.
            parsed = _dt.datetime.strptime(bare, "%Y%m%d").replace(
                hour=23, minute=59, second=59)
    except ValueError as error:      # "2024-01-03" raised a bare ValueError
        raise AutoControlException(f"UNTIL must be YYYYMMDD or YYYYMMDDTHHMMSS[Z], got {value!r}") from error
    return parsed.replace(tzinfo=_dt.timezone.utc) if is_utc else parsed


def _parse_wkst(value: str) -> int:
    wkst = value.strip().upper()
    if wkst not in _WEEKDAYS:        # WKST=XX silently became MO
        raise AutoControlException(f"invalid WKST {value!r}")
    return _WEEKDAYS[wkst]


def _check_combination(freq: str, by_day: Tuple[ByDay, ...], by_month_day: Tuple[int, ...]) -> None:
    """RFC 5545 3.3.10: rule parts that must not appear with this FREQ."""
    if freq == "WEEKLY" and by_month_day:
        raise AutoControlException("BYMONTHDAY must not be given with FREQ=WEEKLY (RFC 5545 3.3.10)")
    if freq in ("DAILY", "WEEKLY") and any(ordinal is not None for ordinal, _ in by_day):
        raise AutoControlException(
            f"a numbered BYDAY (such as 2MO) needs FREQ=MONTHLY or YEARLY, not {freq} (RFC 5545 3.3.10)")


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
    by_day = _parse_byday(parts.get("BYDAY", ""))
    by_month_day = _parse_ints(parts.get("BYMONTHDAY", ""), "BYMONTHDAY", -31, 31)
    _check_combination(freq, by_day, by_month_day)
    return Recurrence(
        freq=freq,
        interval=interval,
        count=count,
        until=_parse_until(parts["UNTIL"]) if "UNTIL" in parts else None,
        by_day=by_day,
        by_month_day=by_month_day,
        by_month=_parse_ints(parts.get("BYMONTH", ""), "BYMONTH", 1, 12),
        by_set_pos=_parse_ints(parts.get("BYSETPOS", ""), "BYSETPOS"),
        wkst=_parse_wkst(parts.get("WKST", "MO")),
    )


# --- candidate selection ---------------------------------------------------

def _apply_time(day: _dt.date, dtstart: _dt.datetime) -> _dt.datetime:
    # With the microseconds too: dropping them put the first occurrence just
    # before DTSTART, which then lost it (RFC 5545: DTSTART is the first).
    return _dt.datetime(day.year, day.month, day.day, dtstart.hour, dtstart.minute,
                        dtstart.second, dtstart.microsecond, tzinfo=dtstart.tzinfo)


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
    days = [week_start + _dt.timedelta(days=offset)
            for offset in range(min(7, (_dt.date.max - week_start).days + 1))]
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
    # The set of one interval is this day: BYSETPOS=1 or -1 keeps it, BYSETPOS=2
    # selects nothing (it was ignored).
    return _setpos([day], rule.by_set_pos)


def _safe_date(year: int, month: int, day: int) -> Optional[_dt.date]:
    if 1 <= day <= monthrange(year, month)[1]:
        return _dt.date(year, month, day)
    return None


def _yearly_dates(year: int, dtstart: _dt.datetime,
                  rule: Recurrence) -> List[_dt.date]:
    if not rule.by_month and rule.by_day:
        # Without BYMONTH a BYDAY ordinal counts within the year (RFC 5545
        # 3.3.10): -1FR is the year's last Friday, 20MO its 20th Monday -- also
        # when BYMONTHDAY narrows the days, where 1MO used to mean the first
        # Monday of every month.
        days = _select_in_year(year, rule.by_day)
        if rule.by_month_day:
            days = [day for day in days if _monthday_ok(day, rule.by_month_day)]
        return _setpos(days, rule.by_set_pos)
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


# --- period series ---------------------------------------------------------

#: A rule is exhausted after this many years without an occurrence, scaled up
#: for a period longer than a year. A fixed 400 years after DTSTART cut real
#: series short (YEARLY;INTERVAL=100 from a 29 February lost 2800); the gap
#: still ends a rule that can never match (BYMONTH=2;BYMONTHDAY=30).
_MAX_GAP_YEARS = 400
_PERIOD_DAYS = {"DAILY": 1, "WEEKLY": 7, "MONTHLY": 31, "YEARLY": 366}
_Period = Tuple[int, List[_dt.date]]


def _add_months(year: int, month: int, delta: int) -> Tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _gap_years(rule: Recurrence) -> int:
    period_years = -(-_PERIOD_DAYS[rule.freq] * rule.interval // 365)
    return _MAX_GAP_YEARS * max(1, period_years)


def _daily_periods(rule: Recurrence, dtstart: _dt.datetime) -> Iterator[_Period]:
    cursor, step = dtstart.date(), _dt.timedelta(days=rule.interval)
    while True:
        yield cursor.year, _daily_dates(cursor, rule)
        if (_dt.date.max - cursor).days < rule.interval:
            return                    # stepping past 9999-12-31 raised OverflowError
        cursor += step


def _weekly_periods(rule: Recurrence, dtstart: _dt.datetime) -> Iterator[_Period]:
    offset = (dtstart.weekday() - rule.wkst) % 7
    cursor = dtstart.date() - _dt.timedelta(days=min(offset, (dtstart.date() - _dt.date.min).days))
    while True:
        yield cursor.year, _weekly_dates(cursor, dtstart, rule)
        if (_dt.date.max - cursor).days < 7 * rule.interval:
            return
        cursor += _dt.timedelta(weeks=rule.interval)


def _monthly_periods(rule: Recurrence, dtstart: _dt.datetime) -> Iterator[_Period]:
    year, month = dtstart.year, dtstart.month
    while year <= _dt.MAXYEAR:
        yield year, _monthly_dates(year, month, dtstart, rule)
        year, month = _add_months(year, month, rule.interval)


def _yearly_periods(rule: Recurrence, dtstart: _dt.datetime) -> Iterator[_Period]:
    year = dtstart.year
    while year <= _dt.MAXYEAR:
        yield year, _yearly_dates(year, dtstart, rule)
        year += rule.interval


_PERIODS = {
    "DAILY": _daily_periods, "WEEKLY": _weekly_periods,
    "MONTHLY": _monthly_periods, "YEARLY": _yearly_periods,
}


def _series(rule: Recurrence, dtstart: _dt.datetime) -> Iterator[_dt.datetime]:
    """Every candidate of ``rule`` in order, until the gap since the last occurrence is too long."""
    gap, last = _gap_years(rule), dtstart.year
    for year, dates in _PERIODS[rule.freq](rule, dtstart):
        if year > last + gap:
            return
        for day in dates:
            moment = _apply_time(day, dtstart)
            if moment >= dtstart:
                last = day.year
            yield moment


# --- public expansion ------------------------------------------------------

def _align(moment: _dt.datetime, dtstart: _dt.datetime) -> _dt.datetime:
    """``moment`` made comparable with ``dtstart``: naive and aware are not."""
    aware_start = dtstart.tzinfo is not None
    aware_moment = moment.tzinfo is not None
    if aware_start and not aware_moment:
        return moment.replace(tzinfo=dtstart.tzinfo)
    if not aware_start and aware_moment:
        # A naive DTSTART is local time: convert a UTC UNTIL to it rather
        # than dropping the offset (20240103T050000Z is 13:00 at +0800).
        return moment.astimezone().replace(tzinfo=None)
    return moment


def _normalize_until(until: Optional[_dt.datetime],
                     dtstart: _dt.datetime) -> Optional[_dt.datetime]:
    return None if until is None else _align(until, dtstart)


def _after_until(moment: _dt.datetime,
                 limit_until: Optional[_dt.datetime]) -> bool:
    return limit_until is not None and moment > limit_until


def _smaller(*limits: Optional[int]) -> Optional[int]:
    given = [limit for limit in limits if limit is not None]
    return min(given) if given else None


def _earlier(*limits: Optional[_dt.datetime]) -> Optional[_dt.datetime]:
    given = [limit for limit in limits if limit is not None]
    return min(given) if given else None


def occurrences(rule: Recurrence, dtstart: _dt.datetime, *,
                count: Optional[int] = None, until: Optional[_dt.datetime] = None,
                max_iter: Optional[int] = 100000) -> Iterator[_dt.datetime]:
    """Yield occurrence datetimes for ``rule`` anchored at ``dtstart``.

    ``count`` and ``until`` narrow the rule's own ``COUNT`` / ``UNTIL`` (the
    smaller wins); they used to replace them, so ``AC_rrule_occurrences``'
    ``count=10`` listed ten dates of a ``COUNT=3`` rule. ``max_iter`` caps a
    rule without a count (``None``: no cap); an explicit count is never cut
    short by it.
    """
    limit_count = _smaller(rule.count, count)
    limit_until = _earlier(_normalize_until(rule.until, dtstart), _normalize_until(until, dtstart))
    # count=0 used to yield one date before checking the limit.
    remaining = limit_count if limit_count is not None else max_iter
    for moment in _series(rule, dtstart):
        if (remaining is not None and remaining < 1) or _after_until(moment, limit_until):
            return
        if moment >= dtstart:
            yield moment
            if remaining is not None:
                remaining -= 1


def next_occurrence(rule: Recurrence, dtstart: _dt.datetime, *,
                    now: Optional[_dt.datetime] = None) -> Optional[_dt.datetime]:
    """Return the first occurrence at or after ``now`` (or ``None`` when the rule has ended).

    A naive ``now`` against an aware ``dtstart`` (or the reverse) is read the
    way ``UNTIL`` is, instead of raising ``TypeError``; and a long-running
    rule is walked to ``now`` however far away it is (DTSTART 1750 used to
    answer ``None`` after 100,000 candidates).
    """
    moment = now if now is not None else _dt.datetime.now(dtstart.tzinfo)
    moment = _align(moment, dtstart)
    for occurrence in occurrences(rule, dtstart, max_iter=None):
        if occurrence >= moment:
            return occurrence
    return None
