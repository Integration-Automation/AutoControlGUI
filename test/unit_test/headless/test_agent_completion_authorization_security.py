"""Only explicitly reviewed current scope may authorize independent completion of original effects."""
from copy import deepcopy
import json

import pytest

from headless.test_agent_completion_authorization import renewal as _renewal, reviewed, create
from je_auto_control.utils.agent_runtime import AgentTaskError, origin_policy

renewal = _renewal


@pytest.mark.parametrize('field', ['review', 'snapshot', 'empty_note', 'spec', 'owner', 'actions'])
def test_renewal_request_cannot_forge_review_or_supply_verification_scope(renewal, field):
    _preview, request = reviewed(renewal)
    if field == 'review':
        request['authorization_review'] = '0' * 64
    elif field == 'snapshot':
        request['snapshot'] = '0' * 64
    elif field == 'empty_note':
        request['note'] = ' '
    else:
        request[field] = {}
    with pytest.raises(AgentTaskError):
        renewal.runtime.recovery.control('create_authorized_completion', request)
    assert len(renewal.runtime.list()) == 1


@pytest.mark.parametrize('change', ['missing', 'corrupt'])
def test_unavailable_original_witness_is_not_modified_or_restored(renewal, change):
    path = origin_policy._path(renewal.old.identifier)
    if change == 'missing':
        path.unlink()
    else:
        path.write_text('{', encoding='utf-8')
    child = create(renewal)
    assert renewal.runtime.finish(child).state == 'succeeded'
    assert not path.exists() if change == 'missing' else path.read_text(encoding='utf-8') == '{'


def test_newly_revoked_issuing_scope_refuses_creation_without_a_child(renewal):
    _preview, request = reviewed(renewal)
    renewal.current.revoke()
    with pytest.raises(AgentTaskError):
        renewal.runtime.recovery.control('create_authorized_completion', request)
    assert len(renewal.runtime.list()) == 1


def test_retained_origin_cannot_be_silently_replaced_after_review(renewal):
    retained = origin_policy.OriginWitness((renewal.reports,))
    try:
        row = renewal.runtime.store.get(renewal.source)
        spec = deepcopy(row['spec'])
        spec['options']['origin_policies'].append(retained.identifier)
        with renewal.runtime.store.connection(write=True) as connection:
            connection.execute('UPDATE agent_tasks SET spec=? WHERE id=?', (json.dumps(spec), renewal.source))
        preview, request = reviewed(renewal)
        assert retained.identifier in preview['authorization']['retained_origins']
        assert retained.identifier in preview['verification_spec']['options']['origin_policies']
        retained.revoke()
        with pytest.raises(AgentTaskError, match='authorization changed'):
            renewal.runtime.recovery.control('create_authorized_completion', request)
        assert len(renewal.runtime.list()) == 1
    finally:
        origin_policy._path(retained.identifier).unlink(missing_ok=True)


@pytest.mark.parametrize('field', ['context', 'kind', 'binding', 'review'])
def test_malformed_private_renewal_is_a_typed_refusal_before_a_reader_starts(renewal, monkeypatch, field):
    from je_auto_control.utils.agent_runtime.readonly_target import ReadOnlyNativeTarget
    child = create(renewal)
    with renewal.runtime.store.connection(write=True) as connection:
        proof = json.loads(connection.execute('SELECT details FROM agent_task_authorizations WHERE task_id=?',
                                              (child,)).fetchone()[0])
        proof[field] = None
        connection.execute('UPDATE agent_task_authorizations SET details=? WHERE task_id=?', (json.dumps(proof), child))
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Malformed renewal must refuse before helper startup')
    monkeypatch.setattr(ReadOnlyNativeTarget, '_launch', forbidden)
    with pytest.raises(AgentTaskError):
        renewal.runtime.finish(child)
    assert child not in renewal.runtime._leases


@pytest.mark.parametrize('finished', [False, True])
def test_another_explicit_renewal_retains_the_previous_reader_root_ceiling(renewal, finished):
    from contextvars import Context
    child = create(renewal)
    if finished:
        assert renewal.runtime.finish(child).state == 'succeeded'
    else:
        renewal.runtime.pause(child)
    renewal.current.revoke()
    next_origin = origin_policy.OriginWitness((renewal.allowed,))
    try:
        def renewed_again():
            with origin_policy.origin_scope(next_origin.identifier):
                preview, request = reviewed(renewal, child)
                assert preview['verification_spec']['roots'] == [str(renewal.reports)]
                final = renewal.runtime.recovery.control('create_authorized_completion', request)['task_id']
                assert renewal.runtime.finish(final).state == 'succeeded'
                assert renewal.runtime.store.get(final)['spec']['roots'] == [str(renewal.reports)]
        Context().run(renewed_again)
    finally:
        origin_policy._path(next_origin.identifier).unlink(missing_ok=True)


def test_a_damaged_previous_reader_cannot_expand_the_ceiling_of_another_renewal(renewal):
    from contextvars import Context
    child = create(renewal)
    renewal.runtime.pause(child)
    row = renewal.runtime.store.get(child)
    row['spec']['roots'] = [str(renewal.allowed)]
    with renewal.runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET spec=? WHERE id=?', (json.dumps(row['spec']), child))
    renewal.current.revoke()
    current = origin_policy.OriginWitness((renewal.allowed,))
    try:
        def forbidden_expansion():
            with origin_policy.origin_scope(current.identifier), pytest.raises(AgentTaskError, match='scope changed'):
                reviewed(renewal, child)
        Context().run(forbidden_expansion)
    finally:
        origin_policy._path(current.identifier).unlink(missing_ok=True)


@pytest.mark.parametrize('renewal', ['active'], indirect=True)
def test_ordinary_completion_cannot_drop_an_explicitly_narrowed_reader_ceiling(renewal):
    from contextvars import Context
    child = create(renewal)
    renewal.runtime.pause(child)
    broader = origin_policy.OriginWitness((renewal.allowed,))
    try:
        def ordinary():
            with origin_policy.origin_scope(broader.identifier):
                with pytest.raises(AgentTaskError, match='explicit'):
                    renewal.runtime.recovery.control('preview_completion', {'task_id': child})
        Context().run(ordinary)
    finally:
        origin_policy._path(broader.identifier).unlink(missing_ok=True)


@pytest.mark.parametrize('field', ['current_origins', 'retained_origins', 'proposed_roots', 'policies'])
def test_a_matching_digest_does_not_make_malformed_context_lists_authoritative(renewal, monkeypatch, field):
    from je_auto_control.utils.agent_runtime.readonly_target import ReadOnlyNativeTarget
    from je_auto_control.utils.agent_runtime.store import request_spec_digest
    child = create(renewal)
    with renewal.runtime.store.connection(write=True) as connection:
        proof = json.loads(connection.execute('SELECT details FROM agent_task_authorizations WHERE task_id=?',
                                              (child,)).fetchone()[0])
        proof['context'][field] = None
        proof['review'] = request_spec_digest(proof['context'])
        connection.execute('UPDATE agent_task_authorizations SET details=? WHERE task_id=?', (json.dumps(proof), child))
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Malformed context must refuse before a reader starts')
    monkeypatch.setattr(ReadOnlyNativeTarget, '_launch', forbidden)
    with pytest.raises(AgentTaskError):
        renewal.runtime.finish(child)


@pytest.mark.parametrize('value', ['null', '[1]', '{', 'missing'])
def test_corrupt_private_readonly_marker_never_falls_back_to_ordinary_input(renewal, value):
    child = create(renewal)
    with renewal.runtime.store.connection(write=True) as connection:
        if value == 'missing':
            connection.execute('DELETE FROM agent_readonly_completions WHERE task_id=?', (child,))
        else:
            connection.execute('UPDATE agent_readonly_completions SET details=? WHERE task_id=?', (value, child))
    with pytest.raises(AgentTaskError):
        renewal.runtime.act(child, renewal.action)
    with pytest.raises(AgentTaskError):
        renewal.runtime.finish(child)
