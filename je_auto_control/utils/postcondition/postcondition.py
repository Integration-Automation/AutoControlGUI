"""Declarative expected-outcome specs for an action, checked against the screen.

After an action an agent (or a replay harness) usually has a concrete expectation: "a dialog
saying 'Saved' should appear AND the Submit button should disable". ``expect_poll`` /
``assert_eventually`` poll a *single condition* but have no notion of an action-bound
*postcondition spec*, and they don't diff against a *before* baseline (so they cannot express
"a NEW dialog appeared" — only "a dialog exists"). ``trajectory_eval`` rubrics are
whole-trajectory, not per-step screen state. ``postcondition`` fills the gap: a small JSON spec
of clauses — ``appears`` / ``disappears`` / ``enabled`` / ``disabled`` / ``text_present`` /
``text_absent`` / ``count`` — evaluated against the after-observation (optionally diffed against
the before-observation), returning a per-clause pass/fail report.

Pure-stdlib over element dicts; deterministic and unit-testable with no device. The spec is
plain JSON so it rides into action files / MCP / the scheduler. Imports no ``PySide6``.
"""
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

Element = Dict[str, Any]
Report = Tuple[bool, str]


@dataclass(frozen=True)
class PostconditionReport:
    """The result of evaluating a postcondition spec: overall ok + per-clause detail."""

    ok: bool
    clauses: List[Dict[str, Any]]
    failed: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Return the report as a plain dict."""
        return asdict(self)


def _matches(element: Element, criteria: Dict[str, Any]) -> bool:
    """Whether an element matches a ``{role?, name?, name_contains?}`` criteria dict."""
    if "role" in criteria and element.get("role") != criteria["role"]:
        return False
    if "name" in criteria and element.get("name") != criteria["name"]:
        return False
    contains = criteria.get("name_contains")
    return not contains or contains in str(element.get("name", ""))


def _appears(after: Sequence[Element], before: Optional[Sequence[Element]],
             param: Dict[str, Any]) -> Report:
    in_after = any(_matches(e, param) for e in after)
    in_before = before is not None and any(_matches(e, param) for e in before)
    ok = in_after and not in_before
    return ok, "appeared" if ok else "not a new appearance"


def _disappears(after: Sequence[Element], before: Optional[Sequence[Element]],
                param: Dict[str, Any]) -> Report:
    if before is None:
        return False, "needs a before frame"
    ok = any(_matches(e, param) for e in before) and \
        not any(_matches(e, param) for e in after)
    return ok, "disappeared" if ok else "still present or never there"


def _enabled_state(after: Sequence[Element], param: Dict[str, Any],
                   want: bool) -> Report:
    for element in after:
        if _matches(element, param):
            return bool(element.get("enabled", True)) == want, \
                f"enabled={element.get('enabled', True)}"
    return False, "element not found"


def _enabled(after, before, param):
    return _enabled_state(after, param, True)


def _disabled(after, before, param):
    return _enabled_state(after, param, False)


def _text(after: Sequence[Element], text: Any, want_present: bool) -> Report:
    found = any(str(text) in str(e.get("name", "")) for e in after)
    return found == want_present, "present" if found else "absent"


def _text_present(after, before, param):
    return _text(after, param, True)


def _text_absent(after, before, param):
    return _text(after, param, False)


def _count(after, before, param: Dict[str, Any]) -> Report:
    number = sum(1 for e in after if _matches(e, param.get("match", {})))
    if "equals" in param:
        return number == int(param["equals"]), f"count={number}"
    if "min" in param:
        return number >= int(param["min"]), f"count={number}"
    return False, "count clause needs 'equals' or 'min'"


_CLAUSES: Dict[str, Callable[[Sequence[Element], Optional[Sequence[Element]],
                                  Dict[str, Any]], Report]] = {
    "appears": _appears, "disappears": _disappears,
    "enabled": _enabled, "disabled": _disabled,
    "text_present": _text_present, "text_absent": _text_absent, "count": _count,
}


def check_postcondition(after: Sequence[Element], spec: Dict[str, Any], *,
                        before: Optional[Sequence[Element]] = None
                        ) -> PostconditionReport:
    """Evaluate a postcondition ``spec`` against the after-frame (optional before-frame)."""
    after_list = list(after)
    before_list = list(before) if before is not None else None
    clauses: List[Dict[str, Any]] = []
    for key, param in spec.items():
        checker = _CLAUSES.get(key)
        if checker is None:
            clauses.append({"type": key, "ok": False, "detail": "unknown clause"})
            continue
        ok, detail = checker(after_list, before_list, param)
        clauses.append({"type": key, "ok": ok, "detail": detail})
    failed = [clause["type"] for clause in clauses if not clause["ok"]]
    return PostconditionReport(ok=not failed, clauses=clauses, failed=failed)


def compile_postcondition(spec: Dict[str, Any]) -> Callable[[Sequence[Element]], bool]:
    """Return a predicate ``after -> bool`` for the spec (for use with ``expect_poll``)."""
    def predicate(after: Sequence[Element]) -> bool:
        return check_postcondition(after, spec).ok
    return predicate
