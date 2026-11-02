"""Owned artifact effects refuse redirected directories, linked files and changed database ownership."""
import errno
import os

import pytest

from headless.test_agent_evidence_cache_ownership import source as _source, expire
from headless.test_agent_transfer_cold_lifecycle import _junction
from je_auto_control.utils.agent_runtime import AgentTaskError

source = _source


@pytest.mark.parametrize('kind', ['namespace', 'task'])
def test_directory_redirection_preserves_foreign_files(source, kind):
    link = source.runtime.evidence.root if kind == 'namespace' else source.runtime.evidence.directory(source.task)
    holding = source.root / 'held-cache'
    foreign = source.root / 'foreign-cache'
    foreign.mkdir()
    sentinel = foreign / 'report.json'
    sentinel.write_bytes(b'foreign bytes must not change')
    assert link.resolve().is_relative_to(source.root.resolve())
    assert holding.resolve().is_relative_to(source.root.resolve()) and not holding.exists()
    link.rename(holding)
    _junction(link, foreign)
    try:
        with pytest.raises(AgentTaskError, match='owner cache'):
            source.runtime.evidence.publish(source.task)
        assert sentinel.read_bytes() == b'foreign bytes must not change'
    finally:
        if os.name == 'nt':
            link.rmdir()
        else:
            link.unlink()
        holding.rename(link)


@pytest.mark.parametrize('name', ['journal.jsonl', 'report.json'])
@pytest.mark.parametrize('operation', ['publish', 'prune'])
def test_hardlinked_artifact_refuses_mutation_and_cleanup(source, name, operation):
    path = source.runtime.evidence.directory(source.task) / name
    foreign = source.root / 'foreign.txt'
    foreign.write_bytes(b'keep this separate file')
    assert path.resolve().is_relative_to(source.root.resolve())
    path.unlink()
    os.link(foreign, path)
    if operation == 'prune':
        expire(source.runtime, source.task)
    with pytest.raises(AgentTaskError, match='ownership'):
        source.runtime.prune() if operation == 'prune' else source.runtime.evidence.publish(source.task)
    assert foreign.read_bytes() == b'keep this separate file' and path.exists()
    assert source.runtime.store.get(source.task)['state'] == 'succeeded'


@pytest.mark.parametrize('name', ['journal.jsonl', 'report.json'])
def test_literal_file_symlink_never_authorizes_artifact_write(source, name):
    path = source.runtime.evidence.directory(source.task) / name
    foreign = source.root / 'foreign.txt'
    foreign.write_bytes(b'preserve symbolic-link destination')
    assert path.resolve().is_relative_to(source.root.resolve())
    path.unlink()
    try:
        path.symlink_to(foreign)
    except OSError as error:
        unavailable = getattr(error, 'winerror', None) == 1314 or error.errno in {
            errno.EACCES, errno.EPERM, errno.ENOSYS, errno.ENOTSUP}
        if unavailable:
            pytest.skip(f'literal file symlink unavailable: {getattr(error, "winerror", error.errno)}')
        raise
    with pytest.raises(AgentTaskError, match='owner cache'):
        source.runtime.evidence.publish(source.task)
    assert foreign.read_bytes() == b'preserve symbolic-link destination'


def test_unowned_journal_lock_is_refused_before_append(source):
    task = source.runtime.submit(source.runtime.store.get(source.task)['spec']).task_id
    source.runtime.store.prepare(task, 'AC_workflow_manifest', {})
    receipt, = source.runtime.store.actions(task)
    directory = source.runtime.evidence.directory(task)
    journal = directory / 'journal.jsonl'
    before = journal.read_bytes()
    foreign = source.root / 'foreign-lock.txt'
    foreign.write_bytes(b'unowned lock destination')
    os.link(foreign, directory / 'journal.jsonl.lock')
    with pytest.raises(AgentTaskError, match='ownership'):
        source.runtime.evidence.action(task, receipt)
    assert journal.read_bytes() == before
    assert foreign.read_bytes() == b'unowned lock destination'


def test_identity_change_after_preflight_stops_prune_before_unlink(source, monkeypatch):
    directory = source.runtime.evidence.directory(source.task)
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    with source.runtime.store.connection() as connection:
        identity = connection.execute('SELECT nonce FROM agent_evidence_identity').fetchone()[0]
    original = source.runtime.evidence.cache.file
    calls = []

    def checked(task, name):
        result = original(task, name)
        calls.append(name)
        if len(calls) == len(before):
            with source.runtime.store.connection(write=True) as connection:
                connection.execute("UPDATE agent_evidence_identity SET nonce='ffffffffffffffffffffffffffffffff'")
        return result

    expire(source.runtime, source.task)
    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(source.runtime.evidence.cache, 'file', checked)
            with pytest.raises(AgentTaskError, match='identity changed'):
                source.runtime.prune()
        assert {path.name: path.read_bytes() for path in directory.iterdir()} == before
        assert source.runtime.store.get(source.task)['state'] == 'succeeded'
    finally:
        with source.runtime.store.connection(write=True) as connection:
            connection.execute('UPDATE agent_evidence_identity SET nonce=?', (identity,))
