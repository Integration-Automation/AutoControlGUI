"""Score an agent's recorded trajectory against a declarative rubric.

An agent *trajectory* is the ordered list of steps a run took, each a dict with
at least an ``"action"`` name (and optionally ``"args"`` / ``"observation"``).
A *rubric* is plain data describing what a good run looks like, so it can live
in a JSON action file or be passed from the MCP/socket surfaces:

* ``required_actions``  — actions that must all appear (set ``ordered: true`` to
  also require they appear in that relative order);
* ``forbidden_actions`` — actions that must never appear;
* ``max_steps``         — an upper bound on trajectory length;
* ``success_contains``  — a substring that must appear in some observation.

:func:`evaluate_trajectory` returns ``{passed, score, steps, checks}`` where the
score is the fraction of applicable checks that passed — a deterministic,
dependency-free signal for agent regression testing. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Mapping, Sequence


def _actions(trajectory: Sequence[Mapping[str, Any]]) -> List[str]:
    return [str(step.get("action", "")) for step in trajectory]


def _check(name: str, passed: bool, detail: str) -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _is_subsequence(needles: Sequence[str], haystack: Sequence[str]) -> bool:
    iterator = iter(haystack)
    return all(needle in iterator for needle in needles)


def _check_required(actions: List[str], required: Sequence[str],
                    ordered: bool) -> Dict[str, Any]:
    present = [a for a in required if a in actions]
    missing = [a for a in required if a not in actions]
    if missing:
        return _check("required_actions", False, f"missing: {missing}")
    if ordered and not _is_subsequence(list(required), actions):
        return _check("required_actions", False,
                      "all present but not in the required order")
    return _check("required_actions", True, f"all present: {present}")


def _check_forbidden(actions: List[str],
                     forbidden: Sequence[str]) -> Dict[str, Any]:
    hit = [a for a in forbidden if a in actions]
    return _check("forbidden_actions", not hit,
                  f"used forbidden: {hit}" if hit else "none used")


def _check_max_steps(steps: int, max_steps: int) -> Dict[str, Any]:
    return _check("max_steps", steps <= max_steps,
                  f"{steps} step(s), limit {max_steps}")


def _check_success(trajectory: Sequence[Mapping[str, Any]],
                   marker: str) -> Dict[str, Any]:
    found = any(marker in str(step.get("observation", ""))
               for step in trajectory)
    return _check("success_contains", found,
                  f"marker {marker!r} {'found' if found else 'not found'}")


def _collect_checks(trajectory: Sequence[Mapping[str, Any]],
                    actions: List[str],
                    rubric: Mapping[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    if "required_actions" in rubric:
        checks.append(_check_required(actions, rubric["required_actions"],
                                      bool(rubric.get("ordered", False))))
    if "forbidden_actions" in rubric:
        checks.append(_check_forbidden(actions, rubric["forbidden_actions"]))
    if "max_steps" in rubric:
        checks.append(_check_max_steps(len(actions), int(rubric["max_steps"])))
    if "success_contains" in rubric:
        checks.append(_check_success(trajectory,
                                     str(rubric["success_contains"])))
    return checks


def evaluate_trajectory(trajectory: Sequence[Mapping[str, Any]],
                        rubric: Mapping[str, Any]) -> Dict[str, Any]:
    """Score ``trajectory`` against ``rubric``; return passed/score/checks.

    ``score`` is the fraction of applicable checks that passed; ``passed`` is
    true only when every applicable check passed. An empty rubric trivially
    passes with a score of ``1.0``.
    """
    actions = _actions(trajectory)
    checks = _collect_checks(trajectory, actions, rubric)
    passed_count = sum(1 for check in checks if check["passed"])
    score = 1.0 if not checks else passed_count / len(checks)
    return {
        "passed": all(check["passed"] for check in checks),
        "score": score,
        "steps": len(actions),
        "checks": checks,
    }
