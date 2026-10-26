"""Real export reviews reject current and retained private caches while ordinary output names stay valid."""
from hashlib import sha256
import sqlite3

import pytest

from headless.test_agent_evidence_cache_legacy import legacy as _legacy
from headless.test_agent_evidence_cache_ownership import source as _source
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.file_target import FileTarget

legacy = _legacy
source = _source


def verified_file(runtime, root, path):
    digest = sha256(path.read_bytes()).hexdigest()
    task = runtime.submit({'goal': 'verify selected bytes', 'target': 'local-files',
        'allowed_tools': ['AC_workflow_manifest'], 'roots': [str(root)],
        'success_criteria': [{'kind': 'file_sha256', 'path': str(path), 'value': digest}]})
    assert runtime.finish(task.task_id).state == 'succeeded'
    return task.task_id


def review(runtime, task):
    return runtime.transfers.control('review_export', {'source_task': task,
        'selection': [{'criterion': 0, 'names': []}], 'recipient_policy': 'caller',
        'idempotency_key': 'cache-privacy-' + task})


@pytest.mark.parametrize('publish', [False, True])
@pytest.mark.parametrize('layout', ['source', 'legacy'])
def test_retained_cache_root_stays_private_after_rebinding_in_a_different_directory(request, layout, publish):
    retained = request.getfixturevalue(layout)
    directory = retained.runtime.evidence.directory(retained.task) if layout == 'source' else retained.directory
    parent = retained.root / 'restored'
    parent.mkdir()
    database = parent / 'runtime.db'
    with sqlite3.connect(retained.runtime.store.path) as original, sqlite3.connect(database) as copy:
        original.backup(copy)
    runtime = AgentRuntime(database, targets={'local-files': FileTarget()})
    try:
        if publish:
            runtime.evidence.publish(retained.task)
        task = verified_file(runtime, retained.root, directory / 'journal.jsonl')
        with pytest.raises(AgentTaskError, match='private runtime'):
            review(runtime, task)
    finally:
        runtime.close()


@pytest.mark.parametrize('name', ['runtime.evidence', '.agent-evidence-cache/' + 'a' * 64])
def test_unrelated_output_directory_names_do_not_become_private_cache_claims(legacy, name):
    path = legacy.root / 'ordinary' / name / 'output.txt'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'ordinary explicitly verified user output')
    task = verified_file(legacy.runtime, legacy.root, path)
    selected = review(legacy.runtime, task)
    assert selected['approval_required'] is True
    assert selected['manifest']['files'][0]['sha256'] == sha256(path.read_bytes()).hexdigest()
