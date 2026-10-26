"""Portable grants must retain actual read-only renewal authority, retirement and reader retention."""
import json
import time

import pytest

from headless.test_agent_completion_authorization import renewal as _renewal, create
from headless.test_agent_transfer_evidence import (
    actual_binding, evidence_server, evidence_review, evidence_create, evidence_read,
)
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.readonly_target import ReadOnlyNativeTarget
from je_auto_control.utils.rbac.authorization import authorization_scope

renewal = _renewal
pytestmark = pytest.mark.parametrize('renewal', ['named_dag'], indirect=True)


def reader(value, monkeypatch):
    with authorization_scope(value.reviewer):
        child = create(value)
        assert value.runtime.finish(child).state == 'succeeded'
    def forbidden(*_args, **_kwargs):
        pytest.fail('A portable renewed reader must not launch input or replay source effects')
    monkeypatch.setattr(ReadOnlyNativeTarget, '_launch', forbidden)
    return child


def test_actual_renewed_reader_exports_only_evidence_without_reviving_old_input(renewal, monkeypatch):
    value = renewal
    child = reader(value, monkeypatch)
    actions = value.runtime.store.actions(value.source)
    output = value.manifest.read_bytes()
    with evidence_server(value.runtime, value.users) as server:
        reviewer_token = value.users.rotate_token('reviewer')
        owner_token = value.users.rotate_token('owner')
        reviewed = evidence_review(server, value.source, child, token=reviewer_token, recipient_policy='source_owner')
        status, created = evidence_create(server, reviewed, token=reviewer_token)
        assert status == 200, created
        identifier = created['evidence']['grant_id']
        binding = actual_binding(value.runtime, value.source)
        status, proof = evidence_read(server, identifier, binding, token=owner_token)
        assert status == 200, proof
        assert proof['task_id'] == child and proof['source_task'] == value.source
        assert proof['evidence_only'] is True and proof['input_authorized'] is False
        assert 'owner' not in proof and str(value.reports) not in json.dumps(proof)
    assert value.runtime.store.actions(value.source) == actions and value.manifest.read_bytes() == output
    assert value.runtime.store.actions(child) == []
    with authorization_scope(value.owner), pytest.raises(AgentTaskError, match='another caller'):
        value.runtime.get(child)


def damage_reader(value, child, change):
    if change == 'reader-origin':
        value.current.revoke()
        return
    with value.runtime.store.connection(write=True) as database:
        if change == 'reader-retention':
            database.execute('UPDATE agent_tasks SET updated=? WHERE id=?', (time.time() - 31 * 86400, child))
        elif change == 'readonly-marker':
            database.execute('DELETE FROM agent_readonly_completions WHERE task_id=?', (child,))
        else:
            database.execute('UPDATE agent_completion SET contract=0 WHERE task_id=?', (child,))


@pytest.mark.parametrize('boundary', ['create', 'resolve'])
@pytest.mark.parametrize('change', ['reader-origin', 'reader-retention', 'readonly-marker', 'completion-contract'])
def test_lost_actual_reader_authority_cannot_create_or_resolve_a_portable_grant(renewal, monkeypatch, boundary, change):
    value = renewal
    child = reader(value, monkeypatch)
    before = value.runtime.store.actions(value.source)
    output = value.manifest.read_bytes()
    with evidence_server(value.runtime, value.users) as server:
        reviewer_token = value.users.rotate_token('reviewer')
        owner_token = value.users.rotate_token('owner')
        reviewed = evidence_review(server, value.source, child, token=reviewer_token, recipient_policy='source_owner')
        identifier = None
        binding = actual_binding(value.runtime, value.source)
        if boundary == 'resolve':
            status, created = evidence_create(server, reviewed, token=reviewer_token)
            assert status == 200, created
            identifier = created['evidence']['grant_id']
            status, proof = evidence_read(server, identifier, binding, token=owner_token)
            assert status == 200, proof
        damage_reader(value, child, change)
        if boundary == 'create':
            status, result = evidence_create(server, reviewed, token=reviewer_token)
            with value.runtime.store.connection() as database:
                count = database.execute("SELECT count(*) FROM agent_transfer_grants WHERE kind='evidence'")
                assert count.fetchone()[0] == 0
        else:
            status, result = evidence_read(server, identifier, binding, token=owner_token)
        assert status == 409, result
    assert value.runtime.store.actions(value.source) == before
    assert value.runtime.store.actions(child) == [] and value.manifest.read_bytes() == output


def test_retained_readonly_consent_still_requires_the_original_batch_issuance_state(renewal, monkeypatch):
    value = renewal
    child = reader(value, monkeypatch)
    with evidence_server(value.runtime, value.users) as server:
        token = value.users.rotate_token('reviewer')
        reviewed = evidence_review(server, value.source, child, token=token, recipient_policy='source_owner')
        batch = value.runtime.store.get(value.source)['spec']['options']['dag_batch']['batch_id']
        with value.runtime.store.connection(write=True) as database:
            database.execute("UPDATE agent_dag_batches SET state='approved' WHERE id=?", (batch,))
        status, result = evidence_create(server, reviewed, token=token)
        assert status == 409, result
        with value.runtime.store.connection() as database:
            count = database.execute("SELECT count(*) FROM agent_transfer_grants WHERE kind='evidence'")
            assert count.fetchone()[0] == 0


@pytest.mark.parametrize('boundary', ['reserve', 'consume_review'])
@pytest.mark.parametrize('change', ['reader-origin', 'completion-contract'])
def test_reader_authority_changed_inside_grant_sql_rolls_back_all_consent(renewal, monkeypatch, boundary, change):
    value = renewal
    child = reader(value, monkeypatch)
    with evidence_server(value.runtime, value.users) as server:
        token = value.users.rotate_token('reviewer')
        reviewed = evidence_review(server, value.source, child, token=token, recipient_policy='source_owner')
        records = value.runtime.transfers.source.records
        original = getattr(records, boundary)
        def changed(connection, *args):
            result = original(connection, *args)
            if change == 'reader-origin':
                value.current.revoke()
            else:
                connection.execute('UPDATE agent_completion SET contract=0 WHERE task_id=?', (child,))
            return result
        monkeypatch.setattr(records, boundary, changed)
        status, result = evidence_create(server, reviewed, token=token)
        assert status == 409, result
        with value.runtime.store.connection() as database:
            for table in ('agent_transfer_grants', 'agent_transfer_intents'):
                count = database.execute('SELECT count(*) FROM ' + table + " WHERE kind='evidence'")
                assert count.fetchone()[0] == 0
    assert value.runtime.store.actions(child) == []
