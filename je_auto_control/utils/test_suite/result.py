"""Result model for the QA suite runner.

A :class:`TestSuiteResult` aggregates one :class:`TestCaseResult` per case;
both are plain dataclasses with ``to_dict`` so they round-trip through JSON
action files, the REST API, and the report generators without any Qt or
third-party dependency.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"

VALID_STATUSES = frozenset({
    STATUS_PASSED, STATUS_FAILED, STATUS_ERROR, STATUS_SKIPPED,
})


@dataclass
class TestCaseResult:
    """Outcome of a single test case."""

    name: str
    status: str
    duration_s: float = 0.0
    message: str = ""
    tags: List[str] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    data_row: Optional[Dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        """True when the case did not fail or error."""
        return self.status in (STATUS_PASSED, STATUS_SKIPPED)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestSuiteResult:
    """Aggregated outcome of a whole suite."""

    name: str
    cases: List[TestCaseResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    duration_s: float = 0.0
    setup_error: Optional[str] = None

    def _count(self, status: str) -> int:
        return sum(1 for case in self.cases if case.status == status)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return self._count(STATUS_PASSED)

    @property
    def failed(self) -> int:
        return self._count(STATUS_FAILED)

    @property
    def errored(self) -> int:
        return self._count(STATUS_ERROR)

    @property
    def skipped(self) -> int:
        return self._count(STATUS_SKIPPED)

    @property
    def success(self) -> bool:
        """True when no case failed/errored and setup succeeded."""
        return (self.failed == 0 and self.errored == 0
                and self.setup_error is None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "started_at": self.started_at,
            "duration_s": self.duration_s,
            "setup_error": self.setup_error,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errored": self.errored,
            "skipped": self.skipped,
            "success": self.success,
            "cases": [case.to_dict() for case in self.cases],
        }
