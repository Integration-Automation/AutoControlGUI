"""Immutable managed skill candidates require a verified trial and explicit version publication."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached
from je_auto_control.utils.agent_runtime.policy import owns_task, durable_payload
from je_auto_control.utils.agent_runtime.skill_parameters import digest, instantiate, parameter_schema, repair_data
from je_auto_control.utils.agent_runtime.skill_recording import (
    recorded_spec, recording_template, assert_verified, verified_skill_actions,
)
from je_auto_control.utils.agent_runtime.skill_completion import check_skill_completion, publication_details
from je_auto_control.utils.agent_runtime.skill_execution import check_skill_execution
from je_auto_control.utils.agent_runtime.handoff_records import HandoffAccess
from je_auto_control.utils.agent_runtime.skill_reauthorization import (
    SkillReauthorization, OPERATIONS as AUTHORIZATION_OPERATIONS, existing_authorization,
)
from je_auto_control.utils.rbac.authorization import current_authorization, AuthorizationError
from je_auto_control.utils.rbac.deferred import DeferredAuthorization

OPERATIONS = ("record", "repair", "list", "get", "preview", "validate", "accept", "run",
              "review_execution") + AUTHORIZATION_OPERATIONS


class AgentSkills:
    """Keep reviewed skills in the task database, separate from mutable legacy action macros."""

    def __init__(self, runtime: Any, *, completion_authority: Callable | None = None,
                 completion_template: Callable | None = None, recovery_review: Callable | None = None) -> None:
        self.runtime = runtime
        self._completion_authority = completion_authority
        self._completion_template = completion_template
        self._recovery_review = recovery_review

    def control(self, operation: str, request: Any = None) -> dict:
        """Perform a fixed owner-scoped skill operation; accepted snapshots never mutate."""
        request = durable_payload(detached({} if request is None else request))
        if not isinstance(request, dict) or not isinstance(operation, str) or operation not in OPERATIONS:
            raise AgentTaskError("unknown skill operation or invalid request")
        if operation in AUTHORIZATION_OPERATIONS:
            return SkillReauthorization(self).control(operation, request)
        handlers = {"record": self._record, "repair": self._repair, "list": self._list,
                    "get": self._get_request, "preview": self._preview, "validate": self._validate,
                    "accept": self._accept, "run": self._run, "review_execution": self._review_execution}
        return handlers[operation](request)

    @staticmethod
    def _fields(request: dict, required: set[str], optional: set[str] | None = None) -> None:
        if not required <= set(request) or set(request) - required - (optional or set()):
            raise AgentTaskError("invalid skill operation fields")

    def _get(self, candidate_id: str) -> dict:
        if not isinstance(candidate_id, str):
            raise AgentTaskError("candidate_id must be a string")
        with self.runtime.store.connection() as connection:
            row = connection.execute("SELECT * FROM agent_skill_candidates WHERE id=?", (candidate_id,)).fetchone()
        if row is None:
            raise AgentTaskError("skill candidate does not exist or belongs to another caller")
        result = dict(row)
        for name in ("owner", "spec", "parameters", "provenance"):
            result[name] = json.loads(result[name])
        if not owns_task(result["owner"], current_authorization()):
            raise AgentTaskError("skill candidate does not exist or belongs to another caller")
        if digest({"spec": result["spec"], "parameters": result["parameters"]}) != result["digest"]:
            raise AgentTaskError("immutable skill candidate digest mismatch")
        with self.runtime.store.connection() as connection:
            publication = connection.execute("SELECT * FROM agent_skill_publications WHERE candidate_id=?",
                                             (candidate_id,)).fetchone()
            result["publication"] = publication_details(connection, publication)
        return result

    def task_pin(self, row: dict) -> dict:
        """Return only a service-bound immutable task pin, never a caller's unsupported version claim."""
        with self.runtime.store.connection() as connection:
            trial = connection.execute("SELECT spec_hash FROM agent_skill_trials WHERE task_id=?",
                                       (row["id"],)).fetchone()
        if trial is None or trial["spec_hash"] != digest(row["spec"]):
            return {}
        return detached(row["spec"]["options"].get("skill_pin", {}))

    def _get_request(self, request: dict) -> dict:
        self._fields(request, {"candidate_id"})
        return self._get(request["candidate_id"])

    def _list(self, request: dict) -> dict:
        self._fields(request, set())
        with self.runtime.store.connection() as connection:
            rows = connection.execute("SELECT id,owner FROM agent_skill_candidates ORDER BY created DESC").fetchall()
        identifiers = [row["id"] for row in rows if owns_task(json.loads(row["owner"]), current_authorization())]
        return {"candidates": [self._get(identifier) for identifier in identifiers[:200]], "total": len(identifiers)}

    def _record(self, request: dict) -> dict:
        self._fields(request, {"task_id", "name"},
                     {"parameters", "validation_criteria", "completion_task_id", "handoff_id"})
        if 'handoff_id' in request and 'completion_task_id' not in request:
            raise AgentTaskError('recording handoff requires an explicit completion_task_id')
        if 'completion_task_id' in request:
            try:
                with DeferredAuthorization.capture().scope():
                    return self._record_completed(request)
            except AuthorizationError as error:
                raise AgentTaskError('skill recording authority changed; review again') from error
        row = self.runtime._row(request["task_id"])
        spec = recorded_spec(self.runtime, row["id"], request.get("validation_criteria"))
        parameters = parameter_schema(spec, request.get("parameters", {}))
        return self._save(request["name"], uuid.uuid4().hex, row["owner"], spec, parameters,
                          {"source_task": row["id"], "kind": "semantic_recording", "parent_version": 0})

    def _record_completed(self, request: dict) -> dict:
        with self.runtime.store.connection(write=True) as connection:
            # pylint: disable-next=protected-access  # reason: retain the runtime's live source ownership boundary
            row = self.runtime._row(request['task_id'])
            selection = self._completion_selection(connection, row, request)
            proof = self._completion_proof(connection, row, selection)
            scope = self._recording_scope(connection, request['completion_task_id'], proof, selection)
            spec = recording_template(self.runtime, row, request.get('validation_criteria'), scope=scope)
            parameters = parameter_schema(spec, request.get('parameters', {}))
            provenance = {'source_task': row['id'], 'kind': 'semantic_recording', 'parent_version': 0,
                          'completion_review': proof}
            candidate = self._candidate(request['name'], uuid.uuid4().hex, row['owner'], spec, parameters, provenance)
            candidate_id = self._insert_candidate(connection, candidate)
            if self._completion_proof(connection, row, self._completion_selection(connection, row, request)) != proof:
                raise AgentTaskError('skill recording proof changed during creation')
            with DeferredAuthorization.capture().scope():
                if not owns_task(row['owner'], current_authorization()):
                    raise AgentTaskError('skill recording ownership changed')
        return self._get(candidate_id)

    def _recording_scope(self, connection: Any, task_id: str, proof: dict,
                         selection: Any = None) -> dict | None:
        if isinstance(selection, HandoffAccess):
            template = detached(selection.read(proof['effect_task'])['spec'])
            template['roots'] = list(selection.policy.spec.roots)
            template['options']['origin_policies'] = list(selection.policy.spec.options.get('origin_policies', []))
            return template
        if 'authorization_review' not in proof:
            return None
        if self._completion_authority is None:
            raise AgentTaskError('runtime has no reviewed skill completion provider')
        scope = self._completion_authority(self.runtime, task_id, connection=connection)
        if not isinstance(scope, dict):
            raise AgentTaskError('renewed skill completion has no approved effect scope')
        return scope['effect_spec']

    def _save(self, name: str, skill_id: str, owner: dict, spec: dict, parameters: dict, provenance: dict) -> dict:
        candidate = self._candidate(name, skill_id, owner, spec, parameters, provenance)
        with self.runtime.store.connection(write=True) as connection:
            candidate_id = self._insert_candidate(connection, candidate)
        return self._get(candidate_id)

    @staticmethod
    def _candidate(name: str, skill_id: str, owner: dict, spec: dict, parameters: dict, provenance: dict) -> dict:
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise AgentTaskError("skill name must have between one and two hundred characters")
        return {'id': uuid.uuid4().hex, 'skill_id': skill_id, 'name': name, 'owner': owner, 'spec': spec,
                'parameters': parameters, 'provenance': provenance,
                'digest': digest({'spec': spec, 'parameters': parameters}),
                'state': 'draft', 'version': 0, 'created': time.time()}

    @staticmethod
    def _insert_candidate(connection: Any, candidate: dict) -> str:
        provenance = candidate['provenance']
        existing = existing_authorization(connection, provenance, candidate['digest'])
        if existing is not None:
            return existing
        fields = ('id', 'skill_id', 'name', 'owner', 'spec', 'parameters', 'provenance',
                  'digest', 'state', 'version', 'created')
        values = tuple(json.dumps(candidate[field]) if field in {'owner', 'spec', 'parameters', 'provenance'}
                       else candidate[field] for field in fields)
        connection.execute('INSERT INTO agent_skill_candidates VALUES (?,?,?,?,?,?,?,?,?,?,?)', values)
        if provenance.get('kind') == 'origin_reauthorization':
            connection.execute('INSERT INTO agent_skill_authorizations VALUES (?,?,?,?)',
                               (provenance['parent'], provenance['reauthorization']['review'],
                                candidate['digest'], candidate['id']))
        return candidate['id']

    def _repair(self, request: dict) -> dict:
        self._fields(request, {"candidate_id", "changes", "note"})
        parent = self._get(request["candidate_id"])
        if parent["state"] != "accepted":
            raise AgentTaskError("repairs require a published skill version")
        note = _note(request["note"])
        spec = repair_data(parent["spec"], request["changes"])
        spec = self.runtime._validated_spec(spec).to_dict()
        slots = {name: {key: value for key, value in slot.items() if key != "default"}
                 for name, slot in parent["parameters"].items()}
        parameters = parameter_schema(spec, slots)
        return self._save(parent["name"], parent["skill_id"], parent["owner"], spec, parameters,
                          {"kind": "semantic_repair", "parent": parent["id"], "parent_version": parent["version"],
                           "changes": request["changes"], "note": note})

    def _materialize(self, candidate: dict, parameters: Any) -> dict:
        spec = instantiate(candidate["spec"], candidate["parameters"], parameters)
        spec["options"]["skill_pin"] = _pin(candidate)
        return self.runtime._validated_spec(spec).to_dict()

    def _preview(self, request: dict) -> dict:
        self._fields(request, {"candidate_id"}, {"parameters"})
        candidate = self._get(request["candidate_id"])
        return {"spec": self._materialize(candidate, request.get("parameters", {})),
                "candidate_id": candidate["id"], "digest": candidate["digest"]}

    def _validate(self, request: dict) -> dict:
        self._fields(request, {"candidate_id"}, {"parameters"})
        candidate = self._get(request["candidate_id"])
        return self._submit(candidate, request.get("parameters", {}), "validation")

    def _submit(self, candidate: dict, parameters: dict, purpose: str) -> dict:
        spec = self._materialize(candidate, parameters)
        task = self.runtime.submit(spec)
        with self.runtime.store.connection(write=True) as connection:
            connection.execute("INSERT INTO agent_skill_trials VALUES (?,?,?,?,?)",
                               (task.task_id, candidate["id"], digest(spec), purpose, time.time()))
        if self.runtime.background is not None:
            self.runtime.background.start(task.task_id)
        return {"task_id": task.task_id, "state": task.state, "candidate_id": candidate["id"],
                "purpose": purpose, "digest": candidate["digest"]}

    def _accept(self, request: dict) -> dict:
        required = {"candidate_id", "task_id", "expected_version", "note"}
        if 'execution_task_id' in request:
            required |= {'execution_task_id', 'execution_review'}
        self._fields(request, required, {'completion_task_id', 'handoff_id'})
        try:
            with DeferredAuthorization.capture().scope():
                return self._publish(request)
        except AuthorizationError as error:
            raise AgentTaskError('skill publication authority changed; review again') from error

    def _review_execution(self, request: dict) -> dict:
        self._fields(request, {'candidate_id', 'task_id', 'execution_task_id'}, {'completion_task_id', 'handoff_id'})
        try:
            with DeferredAuthorization.capture().scope(), self.runtime.store.connection(write=True) as connection:
                candidate = self._get(request['candidate_id'])
                if candidate['state'] != 'draft':
                    raise AgentTaskError('execution review requires an unpublished draft candidate')
                # pylint: disable-next=protected-access  # reason: preserve the ordinary original-trial owner boundary
                row = self.runtime._row(request['task_id'])
                self._check_trial(connection, candidate, row)
                proof = self._execution_proof(connection, row, request)
                self._check_candidate_owner(candidate)
                return {'candidate_id': candidate['id'], 'task_id': row['id'],
                        'execution_review': proof['review'], 'evidence': proof,
                        'expected_version': candidate['provenance']['parent_version'],
                        'approval_required': True, 'publication_inherited': False}
        except AuthorizationError as error:
            raise AgentTaskError('skill execution authority changed; review again') from error

    def _publish(self, request: dict) -> dict:
        note = _note(request["note"])
        expected = request["expected_version"]
        if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
            raise AgentTaskError("expected_version must be a nonnegative integer")
        with self.runtime.store.connection(write=True) as connection:
            candidate = self._get(request['candidate_id'])
            row = self.runtime._row(request['task_id'])
            self._check_trial(connection, candidate, row)
            proof, execution = self._publication_evidence(connection, row, request)
            self._record_publication(connection, candidate, row, note, expected, proof, execution)
            if self._publication_evidence(connection, row, request) != (proof, execution):
                raise AgentTaskError('skill publication evidence changed during publication')
            self._check_candidate_owner(candidate)
        return self._get(candidate["id"])

    @staticmethod
    def _check_candidate_owner(candidate: dict) -> None:
        with DeferredAuthorization.capture().scope():
            if not owns_task(candidate['owner'], current_authorization()):
                raise AgentTaskError('skill candidate ownership changed')

    def _publication_evidence(self, connection: Any, row: dict, request: dict) -> tuple[dict | None, dict | None]:
        if 'execution_task_id' in request:
            execution = self._execution_proof(connection, row, request)
            if request['execution_review'] != execution['review']:
                raise AgentTaskError('skill execution review changed; review the full chain again')
            return None, execution
        if 'completion_task_id' in request:
            return self._completion_proof(connection, row, self._completion_selection(connection, row, request)), None
        if 'handoff_id' in request:
            raise AgentTaskError('handoff requires selected completion or execution evidence')
        assert_verified(row)
        return None, None

    def _execution_proof(self, connection: Any, row: dict, request: dict) -> dict:
        if self._recovery_review is None:
            raise AgentTaskError('runtime has no reviewed skill recovery provider')
        selection = self._completion_selection(connection, row, request)
        review = selection if isinstance(selection, HandoffAccess) else self._recovery_review
        def completed(active: Any, effect: dict, identifier: Any) -> dict:
            selected = selection if isinstance(selection, HandoffAccess) else identifier
            return self._completion_proof(active, effect, selected)
        proof = check_skill_execution(self.runtime, connection, row, request, review,
                                       verified_skill_actions, completed)
        return {**proof, 'review': digest(proof)}

    def _completion_selection(self, connection: Any, row: dict, request: dict) -> Any:
        if 'handoff_id' not in request:
            return request.get('completion_task_id')
        selected = request.get('completion_task_id', request.get('execution_task_id'))
        if not isinstance(selected, str):
            raise AgentTaskError('handoff requires an explicit completion or execution task')
        return self.runtime.recovery.task_handoff_evidence(row['id'], selected, request['handoff_id'],
                                                           connection=connection)

    def _completion_proof(self, connection: Any, row: dict, task_id: Any) -> dict:
        if self._completion_authority is None or self._completion_template is None:
            raise AgentTaskError('runtime has no reviewed skill completion provider')
        return check_skill_completion(self.runtime, connection, row, task_id,
                                      self._completion_authority, self._completion_template, digest)

    @staticmethod
    def _record_publication(connection: Any, candidate: dict, row: dict, note: str, expected: int,
                            proof: dict | None, execution: dict | None = None) -> None:
        latest = connection.execute('SELECT COALESCE(MAX(version),0) FROM agent_skill_candidates WHERE skill_id=?',
                                    (candidate['skill_id'],)).fetchone()[0]
        if latest != expected or candidate['provenance']['parent_version'] != expected:
            raise AgentTaskError('skill version changed; review the current published version')
        cursor = connection.execute("UPDATE agent_skill_candidates SET state='accepted',version=? "
                                    "WHERE id=? AND state='draft'", (expected + 1, candidate['id']))
        if cursor.rowcount != 1:
            raise AgentTaskError('skill candidate was already accepted')
        identity = current_authorization()
        connection.execute('INSERT INTO agent_skill_publications VALUES (?,?,?,?,?)',
                           (candidate['id'], row['id'], identity.user_id if identity else 'local-host',
                            note, time.time()))
        if proof is not None:
            connection.execute('INSERT INTO agent_skill_completions VALUES (?,?)', (candidate['id'], json.dumps(proof)))
        if execution is not None:
            connection.execute('INSERT INTO agent_skill_executions VALUES (?,?)',
                               (candidate['id'], json.dumps(execution)))

    @staticmethod
    def _check_trial(connection: Any, candidate: dict, row: dict) -> None:
        trial = connection.execute("SELECT * FROM agent_skill_trials WHERE task_id=? AND candidate_id=?",
                                   (row["id"], candidate["id"])).fetchone()
        if trial is None or trial["purpose"] != "validation" or digest(row["spec"]) != trial["spec_hash"]:
            raise AgentTaskError("publication requires this exact candidate's verified validation task")
        pin = row["spec"]["options"].get("skill_pin")
        if pin != _pin(candidate):
            raise AgentTaskError("validation task skill snapshot does not match")

    def _run(self, request: dict) -> dict:
        self._fields(request, {"skill_id", "version"}, {"parameters"})
        version = request["version"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise AgentTaskError("run requires an explicitly pinned positive skill version")
        with self.runtime.store.connection() as connection:
            row = connection.execute("SELECT id FROM agent_skill_candidates WHERE skill_id=? AND version=? "
                                     "AND state='accepted'", (request["skill_id"], version)).fetchone()
        if row is None:
            raise AgentTaskError("published skill version is unavailable")
        return self._submit(self._get(row["id"]), request.get("parameters", {}), "execution")


def _note(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise AgentTaskError("skill review requires a bounded nonempty note")
    return value


def _pin(candidate: dict) -> dict:
    return {"candidate_id": candidate["id"], "skill_id": candidate["skill_id"],
            "version": candidate["version"], "digest": candidate["digest"]}
