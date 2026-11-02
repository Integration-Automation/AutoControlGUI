"""Review replacement origin ceilings for explicitly reauthorized successor tasks."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.agent_runtime.origin_policy import review_origin_policies
from je_auto_control.utils.agent_runtime.policy import validate_root_snapshot
from je_auto_control.utils.agent_runtime.store import request_spec_digest
from je_auto_control.utils.rbac.authorization import current_authorization


def prepare_authorization(spec: AgentTaskSpec, snapshot: str) -> dict:
    """Bind review to original task roots and effective live policy intersections, without input."""
    if not isinstance(snapshot, str) or re.fullmatch(r"[0-9a-f]{64}", snapshot) is None:
        raise AgentTaskError("authorization review requires a source snapshot")
    _validate_roots(spec.roots)
    state = review_origin_policies(spec)
    policies = _clipped_policies(spec.roots, state["retained"] + state["current"])
    proposed = list(spec.roots)
    for policy in policies:
        proposed = _intersect(proposed, policy["roots"])
    data = detached({"contract": 1, "source_snapshot": snapshot, "source_origins": state["source"],
        "replaced_origins": list(dict.fromkeys(state["unavailable"])),
        "retained_origins": list(dict.fromkeys(item["id"] for item in state["retained"])),
        "current_origins": [item["id"] for item in state["current"]],
        "source_roots": list(spec.roots), "proposed_roots": proposed, "policies": policies})
    return {"review": request_spec_digest(data), "context": data}


def authorized_template(spec: dict, authorization: dict) -> dict:
    """Retain available prior constraints and bind new live origins within the original ceiling."""
    result = detached(spec)
    context = authorization["context"]
    origins = list(dict.fromkeys(context["retained_origins"] + context["current_origins"]))
    if len(origins) > 16:
        raise AgentTaskError("too many live origin constraints for successor authorization")
    if origins:
        result["options"]["origin_policies"] = origins
    else:
        result["options"].pop("origin_policies", None)
    result["roots"] = list(context["proposed_roots"])
    result["actions"] = []
    return result


def narrowed_template(template: dict, reviewed: dict) -> dict:
    """Permit only equivalent or smaller roots inside the reviewed effective intersection."""
    roots = reviewed["roots"]
    if any(not any(Path(root).is_relative_to(Path(parent)) for parent in template["roots"]) for root in roots):
        raise AgentTaskError("reauthorized roots exceed the reviewed source ceiling")
    result = detached(template)
    result["roots"] = list(roots)
    return result


def authorization_details(authorization: dict, spec: AgentTaskSpec) -> dict:
    """Freeze the exact policy review, approved roots and operator identity for durable provenance."""
    identity = current_authorization()
    return {**authorization, "approved_roots": list(spec.roots),
            "actor": identity.user_id if identity is not None else "local"}


def _validate_roots(roots: Any) -> None:
    try:
        validate_root_snapshot(roots)
    except (OSError, ValueError, RuntimeError):
        raise AgentTaskError("origin roots require a fresh authorization review") from None


def _clipped_policies(roots: Any, policies: list[dict]) -> list[dict]:
    result: dict[str, dict] = {}
    for policy in policies:
        _validate_roots(policy["roots"])
        result[policy["id"]] = {"id": policy["id"], "roots": _intersect(roots, policy["roots"])}
    return list(result.values())


def _intersect(first: Any, second: Any) -> list[str]:
    found = set()
    for left in first:
        for right in second:
            candidate = _overlap(Path(left), Path(right))
            if candidate is not None:
                found.add(candidate)
    result: list[Path] = []
    for path in sorted(found, key=lambda item: (len(item.parts), str(item))):
        if not any(path.is_relative_to(parent) for parent in result):
            result.append(path)
    return [str(path) for path in result]


def _overlap(first: Path, second: Path) -> Path | None:
    if first.is_relative_to(second):
        return first
    return second if second.is_relative_to(first) else None
