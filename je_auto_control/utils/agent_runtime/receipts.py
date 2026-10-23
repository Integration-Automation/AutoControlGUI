"""Owner-reviewed uncertain outcomes and per-row workflow reports without blind replay."""
from __future__ import annotations

import json
import time
from typing import Any, Mapping, Sequence

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.agent_runtime.policy import durable_payload
from je_auto_control.utils.agent_runtime.workflow_values import captures, _matches_action
from je_auto_control.utils.rbac.authorization import current_authorization

_INACTIVE = frozenset({"not_applied", "failed"})


def effective_actions(receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Preserve every attempt durably but exclude proven non-effects from skill progress."""
    return [dict(receipt) for receipt in receipts if receipt["status"] not in _INACTIVE]


def reconcile(store: Any, task_id: str, request: Mapping[str, Any]) -> None:
    """Apply an explicit owner's witness; this operation is never offered to managed task tools."""
    value = durable_payload(detached(request))
    if not isinstance(value, dict) or set(value) - {"action_id", "decision", "note", "result"}:
        raise AgentTaskError("invalid reconciliation fields")
    if value.get("decision") not in {"applied", "not_applied"}:
        raise AgentTaskError("reconciliation decision must be applied or not_applied")
    note = value.get("note")
    if not isinstance(note, str) or not note.strip() or len(note) > 4000:
        raise AgentTaskError("reconciliation requires a bounded human review note")
    if value["decision"] == "applied" and "result" not in value:
        raise AgentTaskError("applied reconciliation requires the independently reviewed result")
    _commit_review(store, task_id, value)


def _commit_review(store: Any, task_id: str, value: dict) -> None:
    identity = current_authorization()
    with store.connection(write=True) as connection:
        action = connection.execute("SELECT status,result FROM agent_actions WHERE id=? AND task_id=?",
                                    (value.get("action_id"), task_id)).fetchone()
        if action is None or action["status"] != "uncertain":
            raise AgentTaskError("only an uncertain action from this task can be reconciled")
        status = "confirmed" if value["decision"] == "applied" else "not_applied"
        connection.execute("INSERT INTO agent_reviews VALUES (?,?,?,?,?,?,?)",
                           (value["action_id"], task_id, value["decision"], value["note"],
                            action["result"], time.time(),
                            identity.user_id if identity is not None else "local"))
        connection.execute("UPDATE agent_actions SET status=?,result=? WHERE id=?",
                           (status, json.dumps(value.get("result")), value["action_id"]))


def row_report(spec: AgentTaskSpec, receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Report success, failed read-back and pending records separately for each workflow row."""
    active = effective_actions(receipts)
    values = captures(spec, active)
    rows: dict[str, list[str]] = {}
    for index, action in enumerate(spec.actions):
        label = action.get("row")
        if label is None:
            continue
        state = _step_state(action, active[index] if index < len(active) else None, values)
        rows.setdefault(str(label), []).append(state)
    return [{"row": label, "status": _row_state(states)} for label, states in rows.items()]


def _step_state(action: Mapping, receipt: Mapping | None, values: Mapping) -> str:
    if receipt is None:
        return "not_started"
    if receipt["status"] != "confirmed":
        return "pending"
    try:
        verified = _matches_action(action, receipt, values)
    except KeyError:
        return "pending"
    return "success" if verified else "failed"


def _row_state(states: list[str]) -> str:
    if "failed" in states:
        return "failed"
    if all(state == "success" for state in states):
        return "success"
    return "not_started" if all(state == "not_started" for state in states) else "pending"
