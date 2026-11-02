"""Unrelated, stale, forged or unretired completion cannot publish a managed skill version."""
import json

import pytest

from headless.test_agent_skill_completion import acceptance, trial as _trial
from je_auto_control.utils.agent_runtime import AgentTaskError

trial = _trial


def assert_unpublished(value):
    with value.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_publications').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_completions').fetchone()[0] == 0
        assert connection.execute('SELECT state FROM agent_skill_candidates WHERE id=?',
                                   (value.candidate['id'],)).fetchone()[0] == 'draft'


@pytest.mark.parametrize('damage', ['binding', 'lineage', 'lineage_snapshot', 'source_snapshot', 'uncertain',
                                   'purpose', 'trial_hash', 'retirement', 'reports', 'report_kind', 'scope'])
def test_corrupt_or_stale_proof_cannot_publish(trial, damage):
    runtime = trial.runtime
    child_spec = dict(runtime.store.get(trial.child_id)['spec'], goal='Unreviewed scope')
    changes = {
        'binding': ('DELETE FROM agent_readonly_completions WHERE task_id=?', (trial.child_id,)),
        'lineage': ('DELETE FROM agent_task_recoveries WHERE task_id=?', (trial.child_id,)),
        'lineage_snapshot': ('UPDATE agent_task_recoveries SET snapshot=? WHERE task_id=?',
                             ('changed', trial.child_id)),
        'source_snapshot': ('UPDATE agent_tasks SET reason=? WHERE id=?', ('changed', trial.task_id)),
        'uncertain': ('UPDATE agent_actions SET status=? WHERE task_id=?', ('uncertain', trial.task_id)),
        'purpose': ('UPDATE agent_skill_trials SET purpose=? WHERE task_id=?', ('execution', trial.task_id)),
        'trial_hash': ('UPDATE agent_skill_trials SET spec_hash=? WHERE task_id=?', ('changed', trial.task_id)),
        'retirement': ('DELETE FROM agent_completion WHERE task_id=?', (trial.child_id,)),
        'reports': ('UPDATE agent_tasks SET verification=? WHERE id=?', ('[]', trial.child_id)),
        'report_kind': ('UPDATE agent_tasks SET verification=? WHERE id=?',
                        (json.dumps([{'kind': 'file_text', 'status': 'passed'}] * 3), trial.child_id)),
        'scope': ('UPDATE agent_tasks SET spec=? WHERE id=?', (json.dumps(child_spec), trial.child_id)),
    }
    with runtime.store.connection(write=True) as connection:
        connection.execute(*changes[damage])
    with pytest.raises(AgentTaskError):
        runtime.skills.control('accept', acceptance(trial))
    assert_unpublished(trial)


@pytest.mark.parametrize('identifier', [None, [], '', 'not-a-reviewed-completion'])
def test_invalid_completion_identity_has_no_publication(trial, identifier):
    with pytest.raises(AgentTaskError):
        trial.runtime.skills.control('accept', {**acceptance(trial), 'completion_task_id': identifier})
    assert_unpublished(trial)


def test_reader_cannot_masquerade_as_the_execution_trial(trial):
    request = acceptance(trial)
    request.pop('completion_task_id')
    request['task_id'] = trial.child_id
    with pytest.raises(AgentTaskError, match='exact candidate'):
        trial.runtime.skills.control('accept', request)
    assert_unpublished(trial)


def test_another_candidate_cannot_borrow_verified_effects(trial):
    other = trial.runtime.skills.control('record', {'task_id': trial.source_id, 'name': 'Different candidate'})
    with pytest.raises(AgentTaskError, match='exact candidate'):
        trial.runtime.skills.control('accept', {**acceptance(trial), 'candidate_id': other['id']})
    assert_unpublished(trial)


@pytest.mark.parametrize('which', ['child_id', 'task_id'])
def test_unwinding_input_witness_blocks_publication(trial, which):
    identifier = getattr(trial, which)
    trial.runtime._executing.add(identifier)
    try:
        with pytest.raises(AgentTaskError, match='retired|stopped'):
            trial.runtime.skills.control('accept', acceptance(trial))
        assert_unpublished(trial)
    finally:
        trial.runtime._executing.discard(identifier)


def test_options_and_success_flags_do_not_create_private_completion_provenance(trial):
    runtime = trial.runtime
    definition = dict(runtime.store.get(trial.child_id)['spec'])
    definition['options'] = {**definition['options'], 'completion_review': {'effect_task': trial.task_id}}
    forged = runtime.submit(definition)
    runtime.store.update(forged.task_id, 'succeeded', verification=runtime.store.get(trial.child_id)['verification'])
    with pytest.raises(AgentTaskError, match='private reviewed'):
        runtime.skills.control('accept', {**acceptance(trial), 'completion_task_id': forged.task_id})
    assert_unpublished(trial)


@pytest.mark.parametrize('damage', ['invalid_json', 'missing_principals', 'float_version'])
def test_malformed_private_binding_returns_typed_refusal(trial, damage):
    with trial.runtime.store.connection(write=True) as connection:
        row = connection.execute('SELECT details FROM agent_readonly_completions WHERE task_id=?',
                                 (trial.child_id,)).fetchone()
        details = json.loads(row[0])
        if damage == 'missing_principals':
            details.pop('reviewer')
        elif damage == 'float_version':
            details['contract'] = 1.0
        encoded = '{' if damage == 'invalid_json' else json.dumps(details)
        connection.execute('UPDATE agent_readonly_completions SET details=? WHERE task_id=?',
                           (encoded, trial.child_id))
    with pytest.raises(AgentTaskError):
        trial.runtime.skills.control('accept', acceptance(trial))
    assert_unpublished(trial)
