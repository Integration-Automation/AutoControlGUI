"""Resolve receipt-backed workflow variables and compare explicit per-step expectations."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, thaw


def transformed(value: Any, operation: str = "identity") -> str:
    """Apply one allowlisted text transformation without evaluation or code execution."""
    if not isinstance(value, str):
        raise AgentTaskError("captured form values must be text")
    transforms = {"identity": lambda text: text, "strip": str.strip, "upper": str.upper,
                  "lower": str.lower, "collapse_whitespace": lambda text: " ".join(text.split())}
    if operation not in transforms:
        raise AgentTaskError("unknown workflow value transformation")
    return transforms[operation](value)


def captures(spec: AgentTaskSpec, receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Read captures only from confirmed actions at their pinned sequence position."""
    values = {}
    for action, receipt in zip(spec.actions, receipts):
        if action.get("capture") and receipt["status"] == "confirmed":
            values[action["capture"]] = receipt["result"]
    return values


def resolve(value: Any, values: Mapping[str, Any]) -> Any:
    """Resolve exact capture objects recursively; external data cannot become command names."""
    if isinstance(value, Mapping):
        if "$capture" in value:
            if set(value) - {"$capture", "transform"} or value["$capture"] not in values:
                raise AgentTaskError("workflow capture is missing or invalid")
            return transformed(values[value["$capture"]], value.get("transform", "identity"))
        return {key: resolve(item, values) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [resolve(item, values) for item in value]
    return value


def expected(action: Mapping[str, Any], values: Mapping[str, Any]) -> tuple[bool, Any]:
    """Return whether this step has a deterministic read-back expectation."""
    if "expect_result" in action:
        return True, thaw(action["expect_result"])
    if "expect_capture" in action:
        return True, transformed(values[action["expect_capture"]], action.get("transform", "identity"))
    return False, None


def complete(spec: AgentTaskSpec, receipts: Sequence[Mapping[str, Any]]) -> bool:
    """Require every pinned action and expectation; partial submission never counts as complete."""
    receipts = [receipt for receipt in receipts if receipt["status"] not in {"not_applied", "failed"}]
    if not spec.actions or len(receipts) != len(spec.actions):
        return False
    values = captures(spec, receipts)
    for action, receipt in zip(spec.actions, receipts):
        if not _matches_action(action, receipt, values):
            return False
    return True


def _matches_action(action: Mapping, receipt: Mapping, values: Mapping) -> bool:
    if receipt["status"] != "confirmed" or receipt["command"] != action["tool"]:
        return False
    if receipt["arguments"] != resolve(action.get("arguments", {}), values):
        return False
    required, value = expected(action, values)
    return not required or receipt["result"] == value
