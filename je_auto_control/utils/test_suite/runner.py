"""SuiteRunner — turn flat action lists into scored test cases.

A *suite* spec is a plain dict so it round-trips through JSON action
files::

    {
      "name": "Login",
      "setup":    [ ...actions run once before the cases... ],
      "teardown": [ ...actions run once after, always... ],
      "cases": [
        {"name": "valid login", "tags": ["smoke"], "actions": [ ... ]},
        {"name": "each user", "actions": [ ... ${row.user} ... ],
         "data": {"kind": "csv", "path": "users.csv"}, "as": "row"}
      ]
    }

Each case runs its actions through the action executor with
``raise_on_error=True``. An :class:`AutoControlAssertionException` marks
the case *failed*; any other exception marks it *error*; a clean run is
*passed*. Cases carrying a ``data`` source expand to one scored case per
row. Quarantined case names (see :mod:`je_auto_control.utils.quarantine`)
are recorded as *skipped* instead of run.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from je_auto_control.utils.exception.exceptions import (
    AutoControlAssertionException, AutoControlException,
)
from je_auto_control.utils.test_suite.result import (
    STATUS_ERROR, STATUS_FAILED, STATUS_PASSED, STATUS_SKIPPED,
    TestCaseResult, TestSuiteResult,
)

# (case_name, case_spec, optional (var_name, row)) tuples.
_ExpandedCase = Tuple[str, Dict[str, Any], Optional[Tuple[str, Dict[str, Any]]]]


def _resolve_executor(executor: Any) -> Any:
    if executor is not None:
        return executor
    from je_auto_control.utils.executor.action_executor import (
        executor as global_executor,
    )
    return global_executor


def _quarantined_keys(respect: bool) -> Set[str]:
    """Return the set of quarantined case names (empty if disabled/absent)."""
    if not respect:
        return set()
    try:
        from je_auto_control.utils.quarantine import quarantined_names
        return set(quarantined_names())
    except (ImportError, OSError, RuntimeError):
        return set()


def _tags_match(case_tags: Iterable[str], wanted: Optional[Set[str]]) -> bool:
    if not wanted:
        return True
    return bool(set(case_tags) & wanted)


def _expand_cases(case_spec: Dict[str, Any]) -> List[_ExpandedCase]:
    """Expand a data-driven case into one entry per row; else a single entry."""
    base = str(case_spec.get("name", "case"))
    data = case_spec.get("data")
    if not data:
        return [(base, case_spec, None)]
    from je_auto_control.utils.data_source import load_rows
    rows = load_rows(data, limit=case_spec.get("limit"))
    as_name = str(case_spec.get("as", "row"))
    return [
        (f"{base}[{index}]", case_spec, (as_name, row))
        for index, row in enumerate(rows)
    ]


def _run_actions(executor: Any, actions: List[Any]) -> Tuple[str, str]:
    """Execute a case body; map the outcome to a (status, message) pair."""
    if not actions:
        return STATUS_PASSED, ""
    try:
        executor.execute_action(actions, raise_on_error=True)
        return STATUS_PASSED, ""
    except AutoControlAssertionException as error:
        return STATUS_FAILED, str(error)
    except (AutoControlException, LookupError, AttributeError,
            OSError, RuntimeError, TypeError, ValueError) as error:
        # Mirrors the executor's raise_on_error re-raise set: the framework
        # family (incl. AutoControlActionNullException), plus LookupError /
        # AttributeError from block handlers subscripting a bad action.
        return STATUS_ERROR, repr(error)


def _run_one_case(executor: Any, name: str, spec: Dict[str, Any],
                  binding: Optional[Tuple[str, Dict[str, Any]]],
                  quarantined: Set[str]) -> TestCaseResult:
    """Run (or skip) a single expanded case and return its result."""
    tags = [str(tag) for tag in spec.get("tags", [])]
    row = binding[1] if binding is not None else None
    if name in quarantined or spec.get("name") in quarantined:
        return TestCaseResult(
            name=name, status=STATUS_SKIPPED, message="quarantined",
            tags=tags, data_row=row,
        )
    if binding is not None:
        executor.variables.set(binding[0], binding[1])
    started = time.monotonic()
    status, message = _run_actions(executor, spec.get("actions") or [])
    return TestCaseResult(
        name=name, status=status, duration_s=time.monotonic() - started,
        message=message, tags=tags, data_row=row,
    )


def run_suite(spec: Dict[str, Any],
              executor: Any = None,
              tags: Optional[Iterable[str]] = None,
              respect_quarantine: bool = True) -> TestSuiteResult:
    """Run a suite spec and return its aggregated :class:`TestSuiteResult`.

    :param spec: the suite definition dict (see module docstring).
    :param executor: action executor to drive (defaults to the global one).
    :param tags: when given, only cases sharing one of these tags run.
    :param respect_quarantine: skip cases listed in the quarantine store.
    """
    if not isinstance(spec, dict):
        raise ValueError("suite spec must be a dict")
    runner = _resolve_executor(executor)
    wanted = {str(tag) for tag in tags} if tags else None
    quarantined = _quarantined_keys(respect_quarantine)
    result = TestSuiteResult(name=str(spec.get("name", "suite")))
    started = time.monotonic()
    setup_error = _run_setup(runner, spec.get("setup"))
    result.setup_error = setup_error
    try:
        if setup_error is None:
            _run_all_cases(runner, spec, wanted, quarantined, result)
    finally:
        # Teardown is "always run after": it must fire even if case execution
        # raises unexpectedly, and prior case results are preserved.
        _run_teardown(runner, spec.get("teardown"))
    result.duration_s = time.monotonic() - started
    return result


def _run_setup(executor: Any, setup: Optional[List[Any]]) -> Optional[str]:
    """Run the optional setup block; return an error string on failure."""
    if not setup:
        return None
    status, message = _run_actions(executor, setup)
    return None if status == STATUS_PASSED else message


def _run_teardown(executor: Any, teardown: Optional[List[Any]]) -> None:
    """Run the optional teardown block; failures are swallowed by design."""
    if teardown:
        _run_actions(executor, teardown)


def _run_all_cases(executor: Any, spec: Dict[str, Any],
                   wanted: Optional[Set[str]], quarantined: Set[str],
                   result: TestSuiteResult) -> None:
    """Expand, filter, and run every case into ``result``."""
    cases = spec.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("suite 'cases' must be a list")
    for case_spec in cases:
        # A non-dict case would raise AttributeError on .get below (escaping the
        # per-case containment in _run_case_spec); score it as an error instead.
        if not isinstance(case_spec, dict):
            result.cases.append(_error_case_result(
                {"name": "case"},
                TypeError(f"case spec must be a dict, got "
                          f"{type(case_spec).__name__}")))
            continue
        if not _tags_match(case_spec.get("tags", []), wanted):
            continue
        _run_case_spec(executor, case_spec, quarantined, result)


def _run_case_spec(executor: Any, case_spec: Dict[str, Any],
                   quarantined: Set[str], result: TestSuiteResult) -> None:
    """Expand and run one case spec; a bad case scores *error*, never aborts."""
    try:
        expanded = _expand_cases(case_spec)
    except (AutoControlException, OSError, LookupError,
            RuntimeError, TypeError, ValueError) as error:
        result.cases.append(_error_case_result(case_spec, error))
        return
    for name, sub_spec, binding in expanded:
        result.cases.append(
            _run_one_case(executor, name, sub_spec, binding, quarantined),
        )


def _error_case_result(case_spec: Dict[str, Any],
                       error: Exception) -> TestCaseResult:
    """Build an *error* result for a case that failed to even expand."""
    return TestCaseResult(
        name=str(case_spec.get("name", "case")), status=STATUS_ERROR,
        message=repr(error),
        tags=[str(tag) for tag in case_spec.get("tags", [])],
    )
