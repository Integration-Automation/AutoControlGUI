"""Soft assertions — accumulate checks across a block, raise them all at the end.

``assertion.assert_all`` takes a **pre-built list of spec dicts up front**. There is no
*scoped accumulator* you sprinkle ``check()`` calls into across interleaved actions and
that raises everything at once on exit — the JUnit5 ``assertAll`` / Playwright
``expect.soft`` / AssertJ ``SoftAssertions`` pattern, the standard ergonomics for
verifying many fields of a form without stopping at the first failure.

Pure-stdlib context manager; imports no ``PySide6``.
"""
from typing import Any, List, Literal

from je_auto_control.utils.exception.exceptions import AutoControlActionException


class SoftAssertions:
    """A scope that records pass/fail checks and raises the aggregate on exit."""

    def __init__(self, raise_on_exit: bool = True):
        self._results: List[tuple] = []
        self._raise_on_exit = bool(raise_on_exit)

    def check(self, condition: Any, message: str = "") -> bool:
        """Record a truthy/falsy ``condition`` (never raises); return its bool."""
        ok = bool(condition)
        self._results.append((ok, str(message) or "assertion failed"))
        return ok

    def check_equal(self, actual: Any, expected: Any, message: str = "") -> bool:
        """Record that ``actual == expected``."""
        return self.check(actual == expected,
                          message or f"expected {expected!r}, got {actual!r}")

    @property
    def failures(self) -> List[str]:
        """The messages of every failed check, in order."""
        return [message for ok, message in self._results if not ok]

    @property
    def passed(self) -> int:
        """How many checks passed."""
        return sum(1 for ok, _message in self._results if ok)

    def assert_all(self) -> None:
        """Raise ``AutoControlActionException`` if any recorded check failed."""
        failures = self.failures
        if failures:
            raise AutoControlActionException(
                f"{len(failures)} soft assertion(s) failed: "
                + "; ".join(failures))

    def __enter__(self) -> "SoftAssertions":
        return self

    def __exit__(self, exc_type, _exc, _tb) -> Literal[False]:
        if exc_type is None and self._raise_on_exit:
            self.assert_all()
        return False
