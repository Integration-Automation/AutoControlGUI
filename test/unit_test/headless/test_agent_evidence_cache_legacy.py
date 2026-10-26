"""An old cache remains nonowned historical provenance when current publication starts a new segment."""
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from headless.test_agent_evidence_cache_ownership import (
    source as _source, artifact_bytes, expire,
)
from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.agent_runtime.file_target import FileTarget

source = _source


@pytest.fixture
def legacy(source):
    directory = source.runtime.evidence.directory(source.task)
    destination = Path(source.runtime.store.path).with_suffix('.evidence') / source.task
    source.runtime.close()
    assert directory.resolve().is_relative_to(source.root.resolve())
    assert destination.resolve().is_relative_to(source.root.resolve())
    if directory != destination:
        assert not destination.exists()
        destination.parent.mkdir(parents=True, exist_ok=True)
        directory.rename(destination)
    with sqlite3.connect(source.runtime.store.path) as connection:
        connection.execute('UPDATE agent_evidence SET journal_path=? WHERE task_id=?',
                           (str(destination / 'journal.jsonl'), source.task))
        connection.execute('UPDATE run_journals SET journal_path=? WHERE journal_run_id=?',
                           (str(destination / 'journal.jsonl'), source.task))
        connection.execute('UPDATE runs SET artifact_path=? WHERE source_id=?',
                           (str(destination / 'report.json'), 'agent:' + source.task))
        connection.execute('DROP TABLE IF EXISTS agent_evidence_identity')
    (destination / 'unowned-keep.txt').write_bytes(b'unknown historical data must remain untouched')
    old_files = {path.name: path.read_bytes() for path in destination.iterdir()}
    runtime = AgentRuntime(source.runtime.store.path, targets={'local-files': FileTarget()})
    try:
        yield SimpleNamespace(runtime=runtime, task=source.task, directory=destination, files=old_files,
                              output=source.output, body=source.body, root=source.root)
    finally:
        runtime.close()


def test_old_layout_status_keeps_original_links_without_creating_or_reading_a_segment(legacy, monkeypatch):
    before = legacy.runtime.evidence.history.list_runs()
    original = Path.iterdir

    def current_only(path):
        assert path != legacy.directory, 'Status must not enumerate an unowned historical cache'
        return original(path)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, 'iterdir', current_only)
        result = legacy.runtime.get(legacy.task)
    assert result.state == 'succeeded' and result.metadata['artifact_cache_state'] == 'historical'
    assert result.metadata['journal_path'] == str(legacy.directory / 'journal.jsonl')
    assert result.to_dict()['metadata']['artifacts'] == []
    assert not legacy.runtime.evidence.directory(legacy.task).exists()
    assert legacy.runtime.evidence.history.list_runs() == before


def test_legacy_publication_preserves_history_and_all_unknown_bytes_without_inspection(legacy, monkeypatch):
    before = legacy.runtime.evidence.history.list_runs()
    original = Path.iterdir

    def current_only(path):
        assert path != legacy.directory, 'Publication must not inspect or claim historical files'
        return original(path)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, 'iterdir', current_only)
        legacy.runtime.evidence.publish(legacy.task)
    current = legacy.runtime.evidence.metadata(legacy.task)
    assert current['artifact_cache_state'] == 'owned'
    assert current['journal_path'] != str(legacy.directory / 'journal.jsonl')
    assert before[0] in legacy.runtime.evidence.history.list_runs()
    assert len(legacy.runtime.evidence.history.list_runs()) == 2
    assert {path.name: path.read_bytes() for path in legacy.directory.iterdir()} == legacy.files
    assert 'report.json' in artifact_bytes(legacy.runtime, legacy.task)
    expire(legacy.runtime, legacy.task)
    assert legacy.runtime.prune()['deleted'] == [legacy.task]
    assert not Path(current['journal_path']).exists()
    assert {path.name: path.read_bytes() for path in legacy.directory.iterdir()} == legacy.files
    assert legacy.output.read_bytes() == legacy.body
