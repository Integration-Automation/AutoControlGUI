"""Assertion combinators — group, poll, and compose the assertion DSL.

The base ``assert_*`` helpers each check exactly one condition and (by
default) raise on the first failure. Real scripts need two patterns the
single-shot helpers cannot express on their own:

* **Soft / grouped assertions** — verify a *batch* of conditions and
  collect every failure before raising, so one run surfaces all the
  broken expectations instead of stopping at the first. See
  :func:`assert_all`.
* **Eventual assertions** — the screen settles asynchronously, so an
  assertion should be *retried* until it holds or a timeout elapses,
  rather than failing on the first (too-early) check. See
  :func:`assert_eventually`.

Both are driven by declarative *assertion specs* — plain dicts of the
form ``{"kind": "text", "text": "Saved", ...}`` — so the exact same
checks are reachable from Python, JSON action files, the socket server,
and MCP without passing Python callables across those boundaries.

The module is GUI-free: it only calls the headless ``assert_*`` layer.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from je_auto_control.utils.assertion.assertions import (
    AssertionResult,
    assert_clipboard,
    assert_file,
    assert_http,
    assert_image,
    assert_pixel,
    assert_process,
    assert_text,
    assert_window,
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlAssertionException,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

# Map each spec ``kind`` to the headless assertion it dispatches to.
_SPEC_DISPATCH: Dict[str, Callable[..., AssertionResult]] = {
    "text": assert_text,
    "image": assert_image,
    "pixel": assert_pixel,
    "window": assert_window,
    "clipboard": assert_clipboard,
    "process": assert_process,
    "file": assert_file,
    "http": assert_http,
}


@dataclass(frozen=True)
class GroupAssertionResult:
    """Aggregate outcome of a batch of assertions."""

    passed: bool
    total: int
    failed: int
    results: List[AssertionResult] = field(default_factory=list)

    @property
    def message(self) -> str:
        """Human-readable summary line."""
        return (
            f"{self.total - self.failed}/{self.total} assertions passed"
            if self.passed else
            f"{self.failed}/{self.total} assertions failed"
        )

    def failures(self) -> List[AssertionResult]:
        """Return only the failing sub-results."""
        return [r for r in self.results if not r.passed]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["message"] = self.message
        return data


def run_assertion_spec(spec: Mapping[str, Any],
                       raise_on_fail: bool = False) -> AssertionResult:
    """Dispatch one declarative assertion ``spec`` to its ``assert_*`` helper.

    ``spec`` must contain a ``"kind"`` key naming a registered assertion
    (``text``/``image``/``pixel``/``window``/``clipboard``); the remaining
    keys are passed through as keyword arguments. ``raise_on_fail`` here
    overrides any value inside the spec so callers (groups, polling) keep
    control of when failures escalate.
    """
    if not isinstance(spec, Mapping):
        raise AutoControlAssertionException(
            f"assertion spec must be a mapping, got {type(spec).__name__}"
        )
    kind = spec.get("kind")
    assert_fn = _SPEC_DISPATCH.get(kind) if isinstance(kind, str) else None
    if assert_fn is None:
        raise AutoControlAssertionException(
            f"unknown assertion kind {kind!r}; "
            f"expected one of {sorted(_SPEC_DISPATCH)}"
        )
    kwargs = {k: v for k, v in spec.items() if k != "kind"}
    kwargs["raise_on_fail"] = bool(raise_on_fail)
    return assert_fn(**kwargs)


def assert_all(specs: Sequence[Mapping[str, Any]],
               raise_on_fail: bool = True) -> GroupAssertionResult:
    """Run every assertion spec, collecting all failures (soft assertions).

    Unlike the single ``assert_*`` helpers, this never short-circuits: it
    evaluates the whole batch so one run reports *every* broken
    expectation. When ``raise_on_fail`` is True and at least one spec
    failed, it raises :class:`AutoControlAssertionException` with a
    summary of all failures **after** running the complete batch.
    """
    results: List[AssertionResult] = []
    for spec in specs:
        results.append(run_assertion_spec(spec, raise_on_fail=False))
    failed = sum(1 for r in results if not r.passed)
    group = GroupAssertionResult(
        passed=(failed == 0), total=len(results),
        failed=failed, results=results,
    )
    if failed:
        autocontrol_logger.info("assert_all: %s", group.message)
        if raise_on_fail:
            detail = "; ".join(r.message for r in group.failures())
            raise AutoControlAssertionException(
                f"assert_all failed ({group.message}): {detail}"
            )
    return group


def assert_any(specs: Sequence[Mapping[str, Any]],
               raise_on_fail: bool = True) -> GroupAssertionResult:
    """Pass when **at least one** assertion spec passes (OR semantics).

    The complement of :func:`assert_all`: useful when any of several
    outcomes is acceptable — e.g. either a success dialog *or* a redirect
    confirms a login worked. Short-circuits on the first passing spec
    (later specs are not evaluated). When every spec fails and
    ``raise_on_fail`` is True it raises :class:`AutoControlAssertionException`
    summarising the attempts.
    """
    results: List[AssertionResult] = []
    for spec in specs:
        result = run_assertion_spec(spec, raise_on_fail=False)
        results.append(result)
        if result.passed:
            break
    any_passed = any(r.passed for r in results)
    failed = sum(1 for r in results if not r.passed)
    group = GroupAssertionResult(
        passed=any_passed, total=len(results),
        failed=failed, results=results,
    )
    if not any_passed:
        autocontrol_logger.info("assert_any: no spec passed")
        if raise_on_fail:
            detail = "; ".join(r.message for r in results)
            raise AutoControlAssertionException(
                f"assert_any failed: none of {len(results)} specs passed: "
                f"{detail}"
            )
    return group


def assert_eventually(spec: Mapping[str, Any],
                      timeout: float = 5.0,
                      interval: float = 0.25,
                      raise_on_fail: bool = True) -> AssertionResult:
    """Retry one assertion ``spec`` until it passes or ``timeout`` elapses.

    Polls at ``interval`` seconds. Returns the first passing result, or —
    once the deadline passes — the last (failing) result. When
    ``raise_on_fail`` is True a still-failing assertion raises
    :class:`AutoControlAssertionException`, annotated with the elapsed
    wait so the timeout is visible in the failure.
    """
    if timeout < 0:
        raise AutoControlAssertionException("timeout must be non-negative")
    poll = max(float(interval), 0.0)
    deadline = time.monotonic() + float(timeout)
    attempts = 0
    last: Optional[AssertionResult] = None
    while True:
        attempts += 1
        last = run_assertion_spec(spec, raise_on_fail=False)
        if last.passed:
            return last
        if time.monotonic() >= deadline:
            break
        time.sleep(min(poll, max(deadline - time.monotonic(), 0.0)))
    message = (
        f"assert_eventually failed after {timeout}s / {attempts} attempts: "
        f"{last.message}"
    )
    autocontrol_logger.info("%s", message)
    if raise_on_fail:
        raise AutoControlAssertionException(message)
    return AssertionResult(
        kind=last.kind, passed=False, message=message,
        expected=last.expected, actual=last.actual,
        screenshot_path=last.screenshot_path,
    )


__all__ = [
    "GroupAssertionResult",
    "assert_all",
    "assert_any",
    "assert_eventually",
    "run_assertion_spec",
]
