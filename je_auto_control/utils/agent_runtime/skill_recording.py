"""Semantic skill drafts retain verified actions, original scope and independent completion evidence."""
from __future__ import annotations

from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.agent_runtime.receipts import effective_actions

_POINT_TOOLS = frozenset({"AC_click_mouse", "AC_set_mouse_position", "AC_mouse_scroll",
                          "AC_press_mouse", "AC_release_mouse"})


def recorded_spec(runtime: Any, task_id: str, criteria: Any = None) -> dict:
    """Record a succeeded flow without inventing success from an agent's stop signal."""
    row = runtime._row(task_id)
    assert_verified(row)
    spec = detached(row["spec"])
    spec["actions"] = _actions(runtime, row)
    spec["mode"] = "skill"
    spec["options"].pop("skill_pin", None)
    if not any(clause["kind"] == "actions_complete" for clause in spec["success_criteria"]):
        spec["success_criteria"].append({"kind": "actions_complete"})
    if criteria is not None:
        if not isinstance(criteria, list) or not criteria:
            raise AgentTaskError("additional skill validation criteria must be a nonempty array")
        spec["success_criteria"].extend(detached(criteria))
    if not independent_evidence(spec):
        raise AgentTaskError("skill publication requires independent completion criteria or semantic read-back")
    return runtime._validated_spec(spec).to_dict()


def _actions(runtime: Any, row: dict) -> list[dict]:
    receipts = effective_actions(runtime.store.actions(row["id"]))
    if not receipts or any(receipt["status"] != "confirmed" for receipt in receipts):
        raise AgentTaskError("skill recording requires confirmed action receipts")
    if any(receipt["command"] in _POINT_TOOLS for receipt in receipts):
        raise AgentTaskError("semantic skill recording requires reviewed selectors instead of ungrounded pointer steps")
    if row["spec"]["mode"] == "skill":
        from je_auto_control.utils.agent_runtime.workflow_values import complete
        if not complete(AgentTaskSpec.from_dict(row["spec"]), receipts):
            raise AgentTaskError("recorded skill receipts do not match the pinned semantic plan")
        return detached(row["spec"]["actions"])
    return [{"tool": receipt["command"], "arguments": receipt["arguments"]} for receipt in receipts]


def assert_verified(row: dict) -> None:
    """Require durable succeeded state and all real completion checks passing."""
    reports = row["verification"]
    if row["state"] != "succeeded" or not reports or any(item["status"] != "passed" for item in reports):
        raise AgentTaskError("skill evidence task must have independently verified success")


def independent_evidence(spec: dict) -> bool:
    """Accept explicit evidence or reviewed semantic read-back, never dispatch-only completion."""
    if any(clause["kind"] != "actions_complete" for clause in spec["success_criteria"]):
        return True
    return any(_read_back(action)
               and ("expect_result" in action or "expect_capture" in action) for action in spec["actions"])


def _read_back(action: dict) -> bool:
    return (action["tool"] in {"AC_workflow_wait", "AC_browser_wait", "AC_browser_read"} or
            action["tool"] == "AC_workflow_control" and action["arguments"].get("operation") in {"get", "state"})
