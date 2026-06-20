"""Detect when an agent loop is stuck, from outside the model.

The dominant computer-use failure mode is an agent burning budget repeating an
action that has no effect — the model usually can't see its own loop, so it must
be caught mechanically by watching the stream of ``(tool, args, result)`` triples.
``LoopGuard`` flags three patterns:

* ``repeat``    — the same ``(tool, args)`` fired many times in a row;
* ``ping_pong`` — two actions alternating A-B-A-B with no progress;
* ``no_op``     — the observation (a screenshot/state digest) never changes.

It complements a step/time budget (which can't tell a productive loop from a
stuck one) and the offline trajectory evaluator. Pure standard library
(``collections`` + ``hashlib``); deterministic; imports no ``PySide6``.
"""
import hashlib
import json
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Optional, Tuple

LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_CRITICAL = "critical"


@dataclass(frozen=True)
class LoopVerdict:
    """The result of observing one step."""

    pattern: Optional[str]   # None | "repeat" | "ping_pong" | "no_op"
    level: str               # "ok" | "warn" | "critical"
    count: int               # length of the detected run


def _args_key(args: Any) -> str:
    try:
        return json.dumps(args, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return repr(args)


def digest_result(obj: Any) -> str:
    """Return a stable short digest of a result/observation (e.g. a frame)."""
    if isinstance(obj, (bytes, bytearray)):
        data = bytes(obj)
    else:
        data = _args_key(obj).encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]


class LoopGuard:
    """Watches a stream of action triples and flags stuck-loop patterns."""

    def __init__(self, *, warn: int = 8, critical: int = 15,
                 window: int = 20) -> None:
        """``warn``/``critical`` are run-length thresholds; ``window`` caps memory."""
        self._warn = warn
        self._critical = critical
        self._events: Deque[Tuple[str, str]] = deque(maxlen=window)

    def reset(self) -> None:
        """Forget all observed steps."""
        self._events.clear()

    def observe(self, tool: str, args: Any = None,
                result_digest: str = "") -> LoopVerdict:
        """Record a step and return the strongest stuck-loop verdict."""
        self._events.append((f"{tool}:{_args_key(args)}", result_digest))
        pattern, count = self._classify()
        return LoopVerdict(pattern, self._level(pattern, count), count)

    def _classify(self) -> Tuple[Optional[str], int]:
        repeat = self._trailing_repeat()
        if repeat >= 2:
            return "repeat", repeat
        ping = self._trailing_ping_pong()
        if ping >= 4:
            return "ping_pong", ping
        no_op = self._trailing_no_op()
        if no_op >= 2:
            return "no_op", no_op
        return None, 0

    def _trailing_repeat(self) -> int:
        keys = [event[0] for event in self._events]
        if not keys:
            return 0
        last = keys[-1]
        count = 0
        for key in reversed(keys):
            if key != last:
                break
            count += 1
        return count

    def _trailing_ping_pong(self) -> int:
        keys = [event[0] for event in self._events]
        if len(keys) < 4 or keys[-1] == keys[-2]:
            return 0
        first, second = keys[-2], keys[-1]
        count = 0
        for index, key in enumerate(reversed(keys)):
            expected = second if index % 2 == 0 else first
            if key != expected:
                break
            count += 1
        return count

    def _trailing_no_op(self) -> int:
        digests = [event[1] for event in self._events]
        if not digests or not digests[-1]:
            return 0
        last = digests[-1]
        count = 0
        for digest in reversed(digests):
            if digest != last:
                break
            count += 1
        return count

    def _level(self, pattern: Optional[str], count: int) -> str:
        if pattern is None:
            return LEVEL_OK
        if count >= self._critical:
            return LEVEL_CRITICAL
        if count >= self._warn:
            return LEVEL_WARN
        return LEVEL_OK


default_loop_guard = LoopGuard()
