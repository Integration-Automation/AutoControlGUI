"""Run-local masking of resolved vault values before application log handlers."""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from threading import RLock
from typing import Iterator, Optional


def _first_match(text: str, start: int, forms: tuple[str, ...]) -> Optional[tuple[int, str]]:
    nearest_index, nearest_form = len(text) + 1, None
    for form in forms:
        index = text.find(form, start)
        if 0 <= index < nearest_index:
            nearest_index, nearest_form = index, form
    return None if nearest_form is None else (nearest_index, nearest_form)


class SecretLogScope:
    """A shared mask for one run and its joined workers, cleared on run exit."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._active = True
        self._forms: set[str] = set()
        self._ordered: tuple[str, ...] = ()

    @property
    def active(self) -> bool:
        """Whether the owning run is still active."""
        with self._lock:
            return self._active

    @property
    def has_values(self) -> bool:
        """Whether formatting a log record is necessary for this run."""
        with self._lock:
            return bool(self._ordered)

    def remember(self, value: str) -> None:
        """Mask the exact value and common Python/JSON escaped representations."""
        if not value:
            return
        forms = {value, repr(value)[1:-1], json.dumps(value)[1:-1],
                 json.dumps(value, ensure_ascii=False)[1:-1]}
        with self._lock:
            if self._active and not forms.issubset(self._forms):
                self._forms.update(forms)
                self._ordered = tuple(sorted(self._forms, key=lambda form: (-len(form), form)))

    def scrub(self, text: str) -> str:
        """Return text with known values replaced in one pass, longest first."""
        with self._lock:
            if not self._ordered:
                return text
            # Literal matching avoids retaining secret-bearing regex patterns in
            # Python's process-wide compile cache after the run has ended.
            chunks: list[str] = []
            cursor = 0
            while (match := _first_match(text, cursor, self._ordered)) is not None:
                index, form = match
                chunks.extend((text[cursor:index], "***"))
                cursor = index + len(form)
            chunks.append(text[cursor:])
            return "".join(chunks)

    def close(self) -> None:
        """Release all values even if an inherited context outlives this run."""
        with self._lock:
            self._active = False
            self._forms.clear()
            self._ordered = ()


_CURRENT: ContextVar[Optional[SecretLogScope]] = ContextVar("je_auto_control_secret_log_scope", default=None)


def current_secret_scope() -> Optional[SecretLogScope]:
    """Return the active run mask for explicit handoff to joined workers."""
    scope = _CURRENT.get()
    return scope if scope is not None and scope.active else None


def remember_secret(value: str) -> None:
    """Register a vault resolution only for the current run's lifetime."""
    scope = current_secret_scope()
    if scope is not None:
        scope.remember(value)


@contextmanager
def bound_secret_scope(scope: Optional[SecretLogScope]) -> Iterator[None]:
    """Bind a worker to its parent's mask without taking ownership of it."""
    token = _CURRENT.set(scope)
    try:
        yield
    finally:
        _CURRENT.reset(token)


@contextmanager
def secret_log_scope() -> Iterator[None]:
    """Reuse a nested run's mask, or create and clear a top-level run mask."""
    if current_secret_scope() is not None:
        yield
        return
    scope = SecretLogScope()
    with bound_secret_scope(scope):
        try:
            yield
        finally:
            scope.close()


# pylint: disable-next=too-few-public-methods  # reason: logging.Filter defines a single public hook
class SecretLogFilter(logging.Filter):
    """Scrub before any handler, including propagated and queued handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Mask formatted messages, cached exception text and stack information."""
        scope = current_secret_scope()
        if scope is None or not scope.has_values:
            return True
        try:
            message = record.getMessage()
        # pylint: disable-next=broad-exception-caught  # reason: match logging handler containment
        except Exception:  # noqa: BLE001  # reason: user-defined formatting must not abort a command
            message = "<unformattable application log record>"
        record.msg = scope.scrub(message)
        record.args = ()
        if record.exc_info:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
            record.exc_info = None
        if record.exc_text:
            record.exc_text = scope.scrub(record.exc_text)
        if record.stack_info:
            record.stack_info = scope.scrub(record.stack_info)
        return True
