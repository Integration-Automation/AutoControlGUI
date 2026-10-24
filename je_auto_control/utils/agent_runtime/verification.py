"""Deterministic completion evidence with explicit passed, failed and unknown states."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from concurrent.futures import CancelledError

from je_auto_control.utils.agent_runtime.errors import AgentTaskError, AgentHumanReview
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.agent_runtime.policy import TaskPolicy
from je_auto_control.utils.postcondition import check_postcondition

KINDS = frozenset({"result_equals", "file_exists", "file_sha256", "file_text", "file_manifest", "screen",
                   "actions_complete", "browser"})


def validate_criteria(criteria: Sequence[Mapping[str, Any]]) -> None:
    """Reject empty, unknown and incomplete completion conditions before execution."""
    for clause in criteria:
        kind = clause.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            raise AgentTaskError("unknown completion criterion")
        _validate_clause(kind, clause)


def _validate_clause(kind: str, clause: Mapping[str, Any]) -> None:
    if kind == "browser":
        from je_auto_control.utils.agent_runtime.browser_verification import validate_browser_clause
        validate_browser_clause(clause)
    if kind == "file_manifest":
        from je_auto_control.utils.agent_runtime.manifest_evidence import validate_manifest_clause
        validate_manifest_clause(clause)
    if kind == "result_equals" and (not isinstance(clause.get("key"), str) or "value" not in clause):
        raise AgentTaskError("result_equals requires key and value")
    if kind == "screen" and not clause.get("spec"):
        raise AgentTaskError("screen completion requires nonempty postconditions")
    if kind in {"file_sha256", "file_text"} and not isinstance(clause.get("value"), str):
        raise AgentTaskError("file completion requires a value")


def verify(policy: TaskPolicy, receipts: Sequence[Mapping[str, Any]],
           observation: Mapping[str, Any], *,
           browser_read: Callable[[Mapping], Any] | None = None) -> list[dict[str, Any]]:
    """Evaluate all clauses against confirmed results and fresh target observations."""
    reports = []
    for clause in policy.spec.success_criteria:
        try:
            passed = _evaluate(clause, policy, receipts, observation, browser_read)
            status = "unknown" if passed is None else ("passed" if passed else "failed")
            reports.append({"kind": clause["kind"], "status": status})
        except (CancelledError, AuthorizationError, AgentHumanReview):
            raise
        except (OSError, UnicodeError, TypeError, ValueError, LookupError, AgentTaskError) as error:
            reports.append({"kind": clause["kind"], "status": "unknown", "reason": type(error).__name__})
    return reports


def _evaluate(clause: Mapping[str, Any], policy: TaskPolicy, receipts: Sequence[Mapping[str, Any]],
              observation: Mapping[str, Any], browser_read: Callable[[Mapping], Any] | None) -> bool | None:
    kind = clause["kind"]
    if kind == "browser":
        value = browser_read(clause) if browser_read is not None else None
        return value if isinstance(value, bool) else None
    if kind == "file_manifest":
        from je_auto_control.utils.agent_runtime.manifest_evidence import manifest_matches
        return manifest_matches(clause, policy)
    if kind == "actions_complete":
        from je_auto_control.utils.agent_runtime.workflow_values import complete
        return complete(policy.spec, receipts)
    if kind == "result_equals":
        return _last_result(clause, receipts)
    if kind == "screen":
        return _screen_evidence(observation, dict(clause["spec"]))
    return _file_evidence(clause, policy)


def _screen_evidence(observation: Mapping, spec: dict) -> bool | None:
    elements = observation.get("elements")
    if not isinstance(elements, (list, tuple)) or observation.get("semantic_observation", True) is not True:
        return None
    if any(not isinstance(item, Mapping) for item in elements):
        return None
    passed = check_postcondition(list(elements), spec).ok
    if observation.get("text_redacted", False) is False:
        return passed
    if observation.get("text_redacted") is not True:
        return None
    if len(spec) != 1:
        return None
    return _partial_text_evidence(spec, passed)


def _partial_text_evidence(spec: dict, passed: bool) -> bool | None:
    if set(spec) == {"text_present"} and isinstance(spec["text_present"], str) and spec["text_present"]:
        return True if passed else None
    if set(spec) == {"text_absent"} and isinstance(spec["text_absent"], str) and spec["text_absent"]:
        return None if passed else False
    return None


def _last_result(clause: Mapping, receipts: Sequence[Mapping[str, Any]]) -> bool | None:
    confirmed = [row for row in receipts if row["status"] == "confirmed"]
    if not confirmed:
        return None
    result = confirmed[-1]["result"]
    if not isinstance(result, Mapping) or clause["key"] not in result:
        return None
    return result[clause["key"]] == clause["value"]


def _file_evidence(clause: Mapping[str, Any], policy: TaskPolicy) -> bool:
    from je_auto_control.utils.script_vars.interpolate import interpolate_value
    path = Path(policy.path(interpolate_value(clause.get("path"), policy.spec.inputs)))
    if not path.is_file():
        return False
    if path.suffix.lower() in {".part", ".crdownload", ".tmp"}:
        return False
    if clause["kind"] == "file_exists":
        return path.stat().st_size >= int(clause.get("min_bytes", 1))
    if path.stat().st_size > 64 * 1024 * 1024:
        raise AgentTaskError("completion evidence file exceeds the read limit")
    if clause["kind"] == "file_sha256":
        return hashlib.sha256(path.read_bytes()).hexdigest() == clause["value"]
    return clause["value"] in path.read_text(encoding="utf-8")
