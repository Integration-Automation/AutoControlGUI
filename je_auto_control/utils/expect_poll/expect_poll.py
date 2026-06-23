"""Retry an arbitrary value until it matches — Playwright-style ``expect.poll``.

``assert_eventually`` can only poll the framework's fixed dict-spec dispatch table
(text / image / pixel / window / clipboard / process / file / http). It cannot retry an
*arbitrary* value: an OCR'd total equalling ``"$42.00"``, a row count stabilising, a
custom predicate. ``expect_poll`` takes any zero-arg ``getter`` and any ``matcher``
predicate and polls until it passes or the timeout elapses, with injectable
``clock`` / ``sleep`` so it is deterministic in tests (the existing helper calls real
``time.sleep``). Ships a small library of matcher factories.

Pure-stdlib, imports no ``PySide6``.
"""
import time
from dataclasses import dataclass
from typing import Any, Callable

from je_auto_control.utils.exception.exceptions import AutoControlActionException

Matcher = Callable[[Any], bool]


@dataclass(frozen=True)
class PollResult:
    """The outcome of a poll: whether it matched, the last value, and timing."""

    ok: bool
    value: Any
    attempts: int
    waited_s: float
    description: str


def to_equal(expected: Any) -> Matcher:
    """Match when the value equals ``expected``."""
    return lambda value: value == expected


def to_contain(item: Any) -> Matcher:
    """Match when ``item`` is contained in the value."""
    return lambda value: item in value


def to_be_greater_than(threshold: Any) -> Matcher:
    """Match when the value is greater than ``threshold``."""
    return lambda value: value > threshold


def to_match_regex(pattern: str) -> Matcher:
    """Match when ``str(value)`` contains a match for ``pattern``."""
    import re
    regex = re.compile(pattern)
    return lambda value: bool(regex.search(str(value)))


def to_be_truthy() -> Matcher:
    """Match when the value is truthy."""
    return bool


def to_be_stable(times: int = 3) -> Matcher:
    """Match once the value has been equal across ``times`` consecutive polls."""
    state = {"last": object(), "count": 0}

    def matcher(value: Any) -> bool:
        if value == state["last"]:
            state["count"] += 1
        else:
            state["last"], state["count"] = value, 1
        return state["count"] >= int(times)

    return matcher


def expect_poll(getter: Callable[[], Any], matcher: Matcher, *,
                timeout_s: float = 5.0, interval_s: float = 0.25,
                describe: Callable[[Any], str] = repr,
                clock: Callable[[], float] = time.monotonic,
                sleep: Callable[[float], None] = time.sleep) -> PollResult:
    """Poll ``getter`` until ``matcher`` passes or ``timeout_s`` elapses.

    Returns a :class:`PollResult` with the final value, attempt count and elapsed
    time. ``clock`` / ``sleep`` are injectable for deterministic tests.
    """
    start = clock()
    deadline = start + float(timeout_s)
    attempts = 0
    value: Any = None
    while True:
        value = getter()
        attempts += 1
        if matcher(value):
            return PollResult(True, value, attempts, round(clock() - start, 4),
                              describe(value))
        if clock() >= deadline:
            return PollResult(False, value, attempts, round(clock() - start, 4),
                              describe(value))
        sleep(float(interval_s))


def assert_poll(getter: Callable[[], Any], matcher: Matcher, *,
                timeout_s: float = 5.0, interval_s: float = 0.25,
                describe: Callable[[Any], str] = repr) -> PollResult:
    """Like :func:`expect_poll` but raise ``AutoControlActionException`` on failure."""
    result = expect_poll(getter, matcher, timeout_s=timeout_s,
                         interval_s=interval_s, describe=describe)
    if not result.ok:
        raise AutoControlActionException(
            f"expect_poll failed after {result.attempts} attempt(s): "
            f"{result.description}")
    return result
