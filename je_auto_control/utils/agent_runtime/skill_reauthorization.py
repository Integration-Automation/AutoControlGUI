"""Review origin renewal into a new immutable candidate without inheriting skill publication."""
from __future__ import annotations

from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.recovery_authorization import (
    prepare_authorization, authorized_template, narrowed_template, authorization_details,
)
from je_auto_control.utils.agent_runtime.skill_parameters import digest
from je_auto_control.utils.rbac.authorization import AuthorizationError, current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.rbac.users import Capability

OPERATIONS = ("review_authorization", "create_authorized")


def source_snapshot(connection: Any, parent: dict) -> str:
    """Require a real published current version and bind review to its immutable candidate."""
    latest = connection.execute("SELECT COALESCE(MAX(version),0) FROM agent_skill_candidates WHERE skill_id=?",
                                (parent["skill_id"],)).fetchone()[0]
    if parent["state"] != "accepted" or parent["publication"] is None or parent["version"] != latest:
        raise AgentTaskError("reauthorization requires the current published skill version")
    return digest({"candidate": parent["id"], "digest": parent["digest"], "version": latest})


def existing_authorization(connection: Any, provenance: dict, spec_hash: str) -> str | None:
    """Find an identical approved candidate and reject publication races inside the insert transaction."""
    if provenance.get("kind") != "origin_reauthorization":
        return None
    row = connection.execute("SELECT candidate_id FROM agent_skill_authorizations "
                             "WHERE source_candidate=? AND review=? AND spec_hash=?",
                             (provenance["parent"], provenance["reauthorization"]["review"], spec_hash)).fetchone()
    if row is not None:
        return row[0]
    latest = connection.execute("SELECT COALESCE(MAX(version),0) FROM agent_skill_candidates "
                                "WHERE skill_id=(SELECT skill_id FROM agent_skill_candidates WHERE id=?)",
                                (provenance["parent"],)).fetchone()[0]
    if latest != provenance["parent_version"]:
        raise AgentTaskError("skill version changed; review authorization again")
    return None


# pylint: disable-next=too-few-public-methods  # reason: a closed two-operation skill renewal collaborator
class SkillReauthorization:
    """Keep plan and parameter slots fixed while explicitly replacing unavailable origin restrictions."""

    def __init__(self, skills: Any) -> None:
        self.skills = skills

    def control(self, operation: str, request: dict) -> dict:
        """Review passively or save a new draft; validation and publication remain separate operations."""
        fields = {"candidate_id"}
        if operation == "create_authorized":
            fields |= {"snapshot", "authorization_review", "spec", "note"}
        if set(request) != fields or not isinstance(request["candidate_id"], str):
            raise AgentTaskError("invalid skill authorization fields")
        runtime = self.skills.runtime
        # pylint: disable-next=protected-access  # reason: serialize with trusted runtime collaborators
        with runtime._lock("skill:" + request["candidate_id"]), DeferredAuthorization.capture().scope():
            identity = current_authorization()
            if identity is not None and not identity.allows(Capability.DRIVE_INPUT):
                raise AuthorizationError("reviewing skill authorization requires drive_input")
            # pylint: disable-next=protected-access  # reason: reuse immutable digest and owner verification
            parent = self.skills._get(request["candidate_id"])
            with runtime.store.connection() as connection:
                snapshot = source_snapshot(connection, parent)
            authorization = prepare_authorization(AgentTaskSpec.from_dict(parent["spec"]), snapshot)
            template = authorized_template(parent["spec"], authorization)
            template["actions"] = parent["spec"]["actions"]
            if operation == "review_authorization":
                return self._review(parent, snapshot, authorization, template)
            return self._create(parent, request, authorization, template)

    def _review(self, parent: dict, snapshot: str, authorization: dict, template: dict) -> dict:
        issues = []
        reviewed: dict | None = None
        try:
            # pylint: disable-next=protected-access  # reason: reviewed templates use the common host/scope validator
            reviewed = self.skills.runtime._validated_spec(template).to_dict()
        except AgentTaskError:
            issues = ["authorization_scope_unavailable"]
        return {"candidate_id": parent["id"], "snapshot": snapshot, "authorization_review": authorization["review"],
                "authorization": authorization["context"], "spec": reviewed, "issues": issues,
                "approval_required": True, "validation_required": True, "publication_inherited": False}

    def _create(self, parent: dict, request: dict, authorization: dict, template: dict) -> dict:
        if (request["snapshot"] != authorization["context"]["source_snapshot"]
                or request["authorization_review"] != authorization["review"]):
            raise AgentTaskError("skill authorization context changed; review authorization again")
        note = request["note"]
        if not isinstance(note, str) or not note.strip() or len(note) > 4000:
            raise AgentTaskError("skill authorization requires a bounded nonempty review note")
        # pylint: disable-next=protected-access  # reason: creation must repeat current host/scope validation
        spec = self.skills.runtime._validated_spec(request["spec"])
        expected = narrowed_template(template, spec.to_dict())
        if digest(expected) != digest(spec.to_dict()):
            raise AgentTaskError("skill authorization must preserve the entire plan, settings and completion criteria")
        provenance = {"kind": "origin_reauthorization", "parent": parent["id"],
                      "parent_version": parent["version"], "note": note,
                      "reauthorization": authorization_details(authorization, spec)}
        # pylint: disable-next=protected-access  # reason: save through the existing immutable candidate transaction
        return self.skills._save(parent["name"], parent["skill_id"], parent["owner"],
                                 spec.to_dict(), parent["parameters"], provenance)
