"""Actual scoped read-only completion exports artifacts without reviving original input authority."""
import json

import pytest

from headless.test_agent_completion_authorization import renewal as _renewal, create
from headless.test_agent_transfer_source import create_for
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.readonly_target import ReadOnlyNativeTarget
from je_auto_control.utils.rbac.authorization import authorization_scope

renewal = _renewal
pytestmark = pytest.mark.parametrize('renewal', ['named', 'named_dag'], indirect=True)


def export_reader(value, monkeypatch):
    with authorization_scope(value.reviewer):
        child = create(value)
        assert value.runtime.finish(child).state == 'succeeded'
    assert value.runtime.store.actions(child) == []
    def forbidden(*_args, **_kwargs):
        raise AssertionError('artifact export cannot launch a helper or replay input')
    monkeypatch.setattr(ReadOnlyNativeTarget, '_launch', forbidden)
    with authorization_scope(value.reviewer):
        review = value.runtime.transfers.control('review_export', {'source_task': child,
            'selection': [{'criterion': 2, 'names': []}], 'recipient_policy': 'caller',
            'idempotency_key': 'approved-export'})
        exported = create_for(value.runtime, review)
    return child, exported


def test_actual_renewed_reader_exports_only_the_selected_file_with_old_input_still_revoked(renewal, monkeypatch):
    before = renewal.runtime.store.actions(renewal.source)
    child, exported = export_reader(renewal, monkeypatch)
    with authorization_scope(renewal.reviewer):
        manifest = renewal.runtime.transfers.peer('export', {'export_id': exported['export_id']})
    assert manifest['source_task'] == child and manifest['files'][0]['name'] == renewal.output.name
    public = json.dumps(exported)
    assert str(renewal.reports) not in public and 'store_path' not in public and 'origin_policies' not in public
    assert renewal.runtime.store.actions(renewal.source) == before
    assert renewal.old.identifier not in renewal.runtime.store.get(child)['spec']['options']['origin_policies']


@pytest.mark.parametrize('change', ['current_origin', 'private_authorization'])
def test_committed_reader_artifact_does_not_outlive_actual_renewal_authority(renewal, monkeypatch, change):
    child, exported = export_reader(renewal, monkeypatch)
    if change == 'current_origin':
        renewal.current.revoke()
    else:
        with renewal.runtime.store.connection(write=True) as connection:
            encoded = connection.execute('SELECT details FROM agent_task_authorizations WHERE task_id=?',
                                         (child,)).fetchone()[0]
            details = json.loads(encoded)
            details['review'] = 'changed private renewal review'
            connection.execute('UPDATE agent_task_authorizations SET details=? WHERE task_id=?',
                               (json.dumps(details), child))
    with authorization_scope(renewal.reviewer), pytest.raises(AgentTaskError):
        renewal.runtime.transfers.peer('chunk', {'export_id': exported['export_id'],
            'sha256': exported['manifest']['files'][0]['chunks'][0]})
