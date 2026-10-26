"""Current journal segments reserve one owned history link and roll back failed or changed identities."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import time

import pytest

from headless.test_agent_evidence_cache_ownership import source as _source, backed_up, artifact_bytes
from je_auto_control.utils.agent_runtime import AgentTaskError

source = _source


def test_competing_first_ensures_create_one_current_segment(source, monkeypatch):
    original_bytes = artifact_bytes(source.runtime, source.task)
    with backed_up(source) as backup:
        barrier = Barrier(2)
        original = backup.evidence.history.list_runs

        def both_prepared(*args, **kwargs):
            barrier.wait(5)
            return original(*args, **kwargs)

        with monkeypatch.context() as scoped:
            scoped.setattr(backup.evidence.history, 'list_runs', both_prepared)
            with ThreadPoolExecutor(max_workers=2) as workers:
                calls = [workers.submit(backup.evidence.ensure, source.task) for _index in range(2)]
                results = [future.result(timeout=5) for future in calls]
        assert results[0] == results[1]
        assert len(backup.evidence.history.list_runs()) == 2
        assert artifact_bytes(source.runtime, source.task) == original_bytes


def test_failed_rebind_preserves_original_rows_and_explicit_retry_creates_one_segment(source):
    original_bytes = artifact_bytes(source.runtime, source.task)
    with backed_up(source) as backup:
        before = backup.evidence.metadata(source.task)
        with backup.store.connection(write=True) as connection:
            connection.execute('CREATE TRIGGER reject_segment BEFORE UPDATE ON agent_evidence '
                               "BEGIN SELECT RAISE(ABORT,'owned segment rejected'); END")
        with pytest.raises(AgentTaskError, match='database operation failed'):
            backup.evidence.ensure(source.task)
        assert backup.evidence.metadata(source.task)['history_id'] == before['history_id']
        assert backup.evidence.metadata(source.task)['journal_path'] == before['journal_path']
        assert len(backup.evidence.history.list_runs()) == 1
        assert artifact_bytes(source.runtime, source.task) == original_bytes
        with backup.store.connection(write=True) as connection:
            connection.execute('DROP TRIGGER reject_segment')
        created = backup.evidence.ensure(source.task)
        assert created['history_id'] != before['history_id']
        assert len(backup.evidence.history.list_runs()) == 2


def test_database_identity_change_inside_rebind_rolls_back_before_acceptance(source):
    original_bytes = artifact_bytes(source.runtime, source.task)
    with backed_up(source) as backup:
        before = backup.evidence.metadata(source.task)
        with backup.store.connection(write=True) as connection:
            identity = connection.execute('SELECT nonce FROM agent_evidence_identity').fetchone()[0]
            connection.execute('CREATE TRIGGER change_segment AFTER UPDATE ON agent_evidence BEGIN '
                               "UPDATE agent_evidence_identity SET nonce='ffffffffffffffffffffffffffffffff'; END")
        with pytest.raises(AgentTaskError, match='identity changed'):
            backup.evidence.ensure(source.task)
        with backup.store.connection() as connection:
            assert connection.execute('SELECT nonce FROM agent_evidence_identity').fetchone()[0] == identity
            row = connection.execute('SELECT history_id,journal_path FROM agent_evidence WHERE task_id=?',
                                     (source.task,)).fetchone()
            assert tuple(row) == (before['history_id'], before['journal_path'])
        assert len(backup.evidence.history.list_runs()) == 1
        assert artifact_bytes(source.runtime, source.task) == original_bytes


def test_damaged_current_history_link_cannot_finish_an_unrelated_run(source):
    with backed_up(source) as backup:
        backup.evidence.ensure(source.task)
        with backup.store.connection(write=True) as connection:
            cursor = connection.execute('INSERT INTO runs(source_type,source_id,script_path,started_at,status) '
                                        "VALUES ('manual','unrelated','',?,'running')", (time.time(),))
            unrelated = cursor.lastrowid
            before = tuple(connection.execute('SELECT * FROM runs WHERE id=?', (unrelated,)).fetchone())
            connection.execute('UPDATE agent_evidence SET history_id=? WHERE task_id=?', (unrelated, source.task))
        backup.evidence.publish(source.task)
        with backup.store.connection() as connection:
            after = tuple(connection.execute('SELECT * FROM runs WHERE id=?', (unrelated,)).fetchone())
        assert after == before
        assert backup.evidence.metadata(source.task)['history_id'] != unrelated
