"""Literal source links and missing selected chunks cannot redirect reviewed exports."""
import base64
import errno
import os
from pathlib import Path
import stat
from uuid import uuid4

import pytest

from headless.test_agent_transfer_source import completed_source, create_for, review_for
from je_auto_control.utils.agent_runtime import AgentTaskError, transfer_files


def _literal_file_link(path, target):
    try:
        path.symlink_to(target)
    except OSError as error:
        if error.errno == errno.EPERM or getattr(error, 'winerror', None) == 1314:
            pytest.skip('literal file symlinks require filesystem privilege')
        raise
    info = path.lstat()
    assert stat.S_ISLNK(info.st_mode)
    if os.name == 'nt':
        assert info.st_reparse_tag == 0xA000000C
    assert path.resolve() == target.resolve()


def _guard_foreign_reads(monkeypatch, foreign):
    original_open = transfer_files.os.open
    attempted = []

    def confined(value, *args, **kwargs):
        if isinstance(value, (str, bytes, os.PathLike)) and Path(value).resolve() == foreign.resolve():
            attempted.append(value)
            raise AssertionError('foreign descriptor opened')
        return original_open(value, *args, **kwargs)

    monkeypatch.setattr(transfer_files.os, 'open', confined)
    return attempted


@pytest.mark.parametrize('location', ['outside', 'inside'])
def test_literal_source_link_cannot_create_a_reviewed_export(tmp_path, monkeypatch, location):
    source_case = tmp_path / 'source'
    source_case.mkdir()
    foreign = (tmp_path if location == 'outside' else source_case) / 'foreign.txt'
    with completed_source(source_case) as (runtime, task, output, body, _users):
        review = review_for(runtime, task)
        foreign.write_bytes(body)
        output.unlink()
        _literal_file_link(output, foreign)
        attempted = _guard_foreign_reads(monkeypatch, foreign)
        with pytest.raises(AgentTaskError):
            create_for(runtime, review)
        assert foreign.read_bytes() == body
        assert not attempted
        assert output.is_symlink()
        with runtime.store.connection() as connection:
            records = runtime.transfers.source.records.entries(connection, 'export')
        assert not any(record['state'] == 'active' for record in records)


@pytest.mark.parametrize('location', ['outside', 'inside'])
def test_committed_export_link_preserves_snapshot_and_current_scope(tmp_path, monkeypatch, location):
    source_case = tmp_path / 'source'
    source_case.mkdir()
    foreign = (tmp_path if location == 'outside' else source_case) / 'foreign.txt'
    with completed_source(source_case) as (runtime, task, output, body, _users):
        review = review_for(runtime, task)
        exported = create_for(runtime, review)
        foreign.write_bytes(b'new unrelated content after snapshot')
        output.unlink()
        _literal_file_link(output, foreign)
        attempted = _guard_foreign_reads(monkeypatch, foreign)
        if location == 'outside':
            with pytest.raises(AgentTaskError):
                runtime.transfers.peer('export', {'export_id': exported['export_id']})
        else:
            manifest = runtime.transfers.peer('export', {'export_id': exported['export_id']})
            assert manifest == review['manifest']
            digest = manifest['files'][0]['chunks'][0]
            chunk = runtime.transfers.peer('chunk', {'export_id': exported['export_id'], 'sha256': digest})
            assert base64.b64decode(chunk['data']) == body
        assert foreign.read_bytes() == b'new unrelated content after snapshot'
        assert not attempted
        assert output.is_symlink()


def test_missing_selected_chunk_does_not_fall_back_to_another_account(tmp_path):
    with completed_source(tmp_path) as (runtime, task, output, body, _users):
        exported = create_for(runtime, review_for(runtime, task))
        digest = exported['manifest']['files'][0]['chunks'][0]
        source = runtime.transfers.source
        with runtime.store.connection() as connection:
            record = source.records.find(connection, exported['export_id'])
        account = record['account']
        other_account = uuid4().hex
        cache = source._cache.store
        cache.put_chunk(other_account, digest, body)
        assert runtime.transfers.peer('chunk', {'export_id': exported['export_id'],
                                                'sha256': digest})['data'] == base64.b64encode(body).decode('ascii')
        with cache._database.connection() as connection:
            deleted = connection.execute('DELETE FROM sync_asset_chunks WHERE user_id=? AND digest=?',
                                         (account, digest)).rowcount
        assert deleted == 1
        with pytest.raises(AgentTaskError):
            runtime.transfers.peer('chunk', {'export_id': exported['export_id'], 'sha256': digest})
        assert cache.read_chunk(other_account, digest) == body
        assert output.read_bytes() == body
        assert runtime.transfers.peer('export', {'export_id': exported['export_id']}) == exported['manifest']
