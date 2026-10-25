"""Real standard helpers prove exact partial skill execution and optional read-only final verification."""
import json

import pytest

from headless.test_agent_skill_execution import successor
from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.agent_runtime.runner import run_task


@pytest.mark.parametrize('readonly', [False, True])
def test_real_file_helpers_publish_complete_original_effects_without_replaying(tmp_path, monkeypatch, readonly):
    document = tmp_path / 'result.txt'
    document.write_text('complete', encoding='utf-8')
    manifests = [tmp_path / 'first.json', tmp_path / 'last.json']
    actions = [{'tool': 'AC_workflow_manifest', 'arguments': {
        'directory': str(tmp_path), 'path': str(path), 'names': ['result.txt']}} for path in manifests]
    definition = {'goal': 'Validate exact owned-file effects across reviewed recovery', 'target': 'local-files',
                  'mode': 'skill', 'roots': [str(tmp_path)], 'allowed_tools': ['AC_workflow_manifest'],
                  'actions': actions, 'success_criteria': [{'kind': 'actions_complete'},
                      {'kind': 'file_exists', 'path': str(manifests[-1])},
                      {'kind': 'file_text', 'path': str(document), 'value': 'complete'}]}
    target = NativeDesktopTarget(resource_path=tmp_path / 'owned-input.lock')
    runtime = AgentRuntime(tmp_path / 'tasks.sqlite', targets={'local-files': target})
    try:
        source = runtime.submit(definition)
        assert run_task(runtime, source.task_id).state == 'succeeded'
        candidate = runtime.skills.control('record', {'task_id': source.task_id, 'name': 'Actual file chain'})
        trial = runtime.skills.control('validate', {'candidate_id': candidate['id']})
        frame = runtime.observe(trial['task_id'])
        runtime.act(trial['task_id'], {**actions[0], 'observation_id': frame.observation_id})
        runtime.pause(trial['task_id'])
        leaf = successor(runtime, trial['task_id'])
        request = {'candidate_id': candidate['id'], 'task_id': trial['task_id'],
                   'execution_task_id': leaf['task_id']}
        if readonly:
            frame = runtime.observe(leaf['task_id'])
            runtime.act(leaf['task_id'], {**actions[1], 'observation_id': frame.observation_id})
            runtime.pause(leaf['task_id'])
            preview = runtime.recovery.control('preview_completion', {'task_id': leaf['task_id']})
            reader = runtime.recovery.control('create_completion', {'task_id': leaf['task_id'],
                'snapshot': preview['snapshot'], 'note': 'Reviewed actual final file effects for read-only checks'})
            assert runtime.finish(reader['task_id']).state == 'succeeded'
            request['completion_task_id'] = reader['task_id']
        else:
            assert run_task(runtime, leaf['task_id']).state == 'succeeded'
        before = [path.read_bytes() for path in manifests]
        def forbidden(*_args, **_kwargs):
            raise AssertionError('Review/publication must never replay or probe file effects')
        monkeypatch.setattr(target, 'perform', forbidden)
        monkeypatch.setattr(target, 'observe', forbidden)
        review = runtime.skills.control('review_execution', request)
        accepted = runtime.skills.control('accept', {**request, 'execution_review': review['execution_review'],
            'expected_version': 0, 'note': 'Reviewed complete actual effects and independent file criteria'})
        proof = accepted['publication']['execution_review']
        assert accepted['publication']['task_id'] == trial['task_id']
        assert 'completion_review' not in accepted['publication']
        assert proof['verification_task'] == request.get('completion_task_id', leaf['task_id'])
        if readonly:
            assert proof['completion_review']['effect_task'] == leaf['task_id']
        assert runtime.get(trial['task_id']).state == 'paused'
        assert len(runtime.store.actions(trial['task_id'])) == len(runtime.store.actions(leaf['task_id'])) == 1
        assert [path.read_bytes() for path in manifests] == before
        assert 'arguments' not in json.dumps(proof)
    finally:
        runtime.close()
