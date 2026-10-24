"""Explicit per-node decisions preserve graph scope and never reset a possible delivery claim."""
from __future__ import annotations

from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.agent_runtime.store import request_spec_digest
from je_auto_control.utils.agent_runtime.recovery_authorization import (
    prepare_authorization, authorized_template, narrowed_template,
)
from je_auto_control.utils.agent_runtime.dag_continuation_evidence import (
    ContinuationEvidence, completion, semantic_task,
)


def dispatch_template(runtime: Any, node: dict, snapshot: str) -> tuple[dict, dict | None]:
    """Renew only local unavailable origin restrictions; remote authority stays at its destination."""
    source = node["task"]["spec"]
    if node["host"] != "local":
        return detached(source), None
    authority = prepare_authorization(AgentTaskSpec.from_dict(source), snapshot)
    template = authorized_template(source, authority)
    template["actions"] = source["actions"]
    # pylint: disable-next=protected-access  # reason: use the same current profile/tool/criteria validator
    return runtime._validated_spec(template).to_dict(), authority


def validate_decision(runtime: Any, decision: dict, node: dict, phase: str,
                      original: dict | None, evidence: ContinuationEvidence, snapshot: str) -> dict:
    """Return frozen adoption/dispatch proof for one explicitly selected logical node."""
    action = decision.get("action")
    if not isinstance(action, str):
        raise AgentTaskError("invalid DAG continuation action")
    if action == "dispatch":
        return _dispatch(runtime, decision, node, phase, original, snapshot)
    if action in {"adopt", "successor"}:
        return _adopt(decision, node, phase, original, evidence)
    if action == "wait" and set(decision) == {"node_id", "action"}:
        return {"decision": decision, "ready": False, "original": semantic_task(original)}
    raise AgentTaskError("invalid DAG continuation decision")


def _dispatch(runtime: Any, decision: dict, node: dict, phase: str,
              original: dict | None, snapshot: str) -> dict:
    if set(decision) != {"node_id", "action", "spec"} or phase != "pending" or original is not None:
        raise AgentTaskError("DAG dispatch requires a never-claimed node with no accepted destination request")
    template, authority = dispatch_template(runtime, node, snapshot)
    if node["host"] == "local":
        # pylint: disable-next=protected-access  # reason: full live validation precedes explicit approval
        spec = runtime._validated_spec(decision["spec"]).to_dict()
        template = narrowed_template(template, spec)
    else:
        spec = AgentTaskSpec.from_dict(decision["spec"]).to_dict()
    if request_spec_digest(spec) != request_spec_digest(template):
        raise AgentTaskError("DAG continuation must preserve the full node plan and authority ceiling")
    return {"decision": {**decision, "spec": spec}, "ready": True, "original": None, "authority": authority}


def _adopt(decision: dict, node: dict, phase: str, original: dict | None, evidence: ContinuationEvidence) -> dict:
    if set(decision) != {"node_id", "action", "task_id"} or original is None:
        raise AgentTaskError("DAG adoption requires a verified accepted original request")
    if phase == "pending":
        raise AgentTaskError("DAG adoption requires the original coordinator's pre-delivery claim")
    identifier = decision["task_id"]
    if not isinstance(identifier, str) or not identifier or len(identifier) > 256:
        raise AgentTaskError("DAG adoption requires a bounded task identity")
    chain: list[dict] = []
    if decision["action"] == "adopt":
        if identifier != original.get("task_id"):
            raise AgentTaskError("DAG adoption task differs from the bound original request")
        completion(original, node)
        candidate = original
    else:
        candidate, chain = evidence.successor(node, original, identifier)
    return {"decision": decision, "ready": True, "original": semantic_task(original),
            "adopted": semantic_task(candidate), "chain": chain}
