"""Real database backup, publication and retention must preserve another runtime's task evidence."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.file_target import FileTarget


@pytest.fixture
def source(tmp_path):
    output = tmp_path / 'output.txt'
    body = b'actual independently verified user output'
    output.write_bytes(body)
    runtime = AgentRuntime(tmp_path / 'runtime.sqlite', targets={'local-files': FileTarget()})
    try:
        task = runtime.submit({'goal': 'verify own output', 'target': 'local-files',
            'allowed_tools': ['AC_workflow_manifest'], 'roots': [str(tmp_path)],
            'success_criteria': [{'kind': 'file_sha256', 'path': str(output), 'value': sha256(body).hexdigest()}]})
        assert runtime.finish(task.task_id).state == 'succeeded'
        yield SimpleNamespace(runtime=runtime, task=task.task_id, output=output, body=body, root=tmp_path)
    finally:
        runtime.close()


@contextmanager
def backed_up(value):
    path = value.root / 'runtime.db'
    with sqlite3.connect(value.runtime.store.path) as original, sqlite3.connect(path) as copy:
        original.backup(copy)
    runtime = AgentRuntime(path, targets={'local-files': FileTarget()})
    try:
        yield runtime
    finally:
        runtime.close()


def artifact_bytes(runtime, task):
    directory = runtime.evidence.directory(task)
    assert directory.is_dir(), 'Another database removed the original evidence directory'
    return {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}


def expire(runtime, task):
    with runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET updated=? WHERE id=?', (time.time() - 31 * 86400, task))


def test_actual_backup_prune_preserves_unexpired_source_evidence_and_user_output(source):
    original = artifact_bytes(source.runtime, source.task)
    link = source.runtime.evidence.metadata(source.task)
    with backed_up(source) as backup:
        expire(backup, source.task)
        assert backup.prune()['deleted'] == [source.task]
        assert source.runtime.get(source.task).state == 'succeeded'
        assert artifact_bytes(source.runtime, source.task) == original
        assert source.runtime.evidence.metadata(source.task) == link
        assert source.output.read_bytes() == source.body
        with pytest.raises(AgentTaskError, match='does not exist'):
            backup.get(source.task)


def test_backup_publication_creates_own_segment_without_mutating_original_history(source):
    original = artifact_bytes(source.runtime, source.task)
    source_link = source.runtime.evidence.metadata(source.task)
    with backed_up(source) as backup:
        old_link = backup.evidence.metadata(source.task)
        old_run = backup.evidence.history.list_runs()[0]
        backup.evidence.publish(source.task)
        new_link = backup.evidence.metadata(source.task)
        assert new_link['history_id'] != old_link['history_id']
        assert new_link['journal_path'] != old_link['journal_path']
        assert Path(new_link['journal_path']).parent == backup.evidence.directory(source.task)
        assert backup.evidence.directory(source.task) != source.runtime.evidence.directory(source.task)
        runs = backup.evidence.history.list_runs()
        assert len(runs) == 2 and old_run in runs
        old_journals = backup.evidence.history.journals_for_run(old_run.id)
        assert [item.journal_path for item in old_journals] == [old_link['journal_path']]
        backup.evidence.publish(source.task)
        assert backup.evidence.metadata(source.task)['history_id'] == new_link['history_id']
        assert len(backup.evidence.history.list_runs()) == 2
        assert artifact_bytes(source.runtime, source.task) == original
        assert source.runtime.evidence.metadata(source.task) == source_link


def test_same_database_restart_keeps_its_owned_segment_and_prunes_only_owned_files(source):
    link = source.runtime.evidence.metadata(source.task)
    source.runtime.close()
    runtime = AgentRuntime(source.runtime.store.path, targets={'local-files': FileTarget()})
    try:
        runtime.evidence.publish(source.task)
        assert runtime.evidence.metadata(source.task)['journal_path'] == link['journal_path']
        assert runtime.evidence.metadata(source.task)['history_id'] == link['history_id']
        assert len(runtime.evidence.history.list_runs()) == 1
        expire(runtime, source.task)
        assert runtime.prune()['deleted'] == [source.task]
        assert not Path(link['journal_path']).exists()
        assert source.output.read_bytes() == source.body
    finally:
        runtime.close()
