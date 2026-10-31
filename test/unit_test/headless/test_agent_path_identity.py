"""Identity checks accept Windows' extended-length spelling of the same path and nothing else."""
import os
from pathlib import Path

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskError, path_identity
from je_auto_control.utils.agent_runtime.evidence_cache import _directory

EXTENDED = '\\\\?\\'


@pytest.mark.parametrize(('text', 'expected'), [
    (EXTENDED + 'C:\\Users\\a\\cache', 'C:\\Users\\a\\cache'),
    (EXTENDED + 'UNC\\server\\share\\cache', '\\\\server\\share\\cache'),
    ('C:\\Users\\a\\cache', 'C:\\Users\\a\\cache'),
    (EXTENDED + 'GLOBALROOT\\Device\\HarddiskVolume1\\cache', EXTENDED + 'GLOBALROOT\\Device\\HarddiskVolume1\\cache'),
    (EXTENDED + 'Volume{0}\\cache', EXTENDED + 'Volume{0}\\cache'),
    (EXTENDED + 'C:', EXTENDED + 'C:'),
    ('/tmp/cache', '/tmp/cache'),
])
def test_only_a_drive_or_unc_prefix_is_dropped(text, expected):
    assert path_identity.plain_spelling(text) == expected


def _prefixing_resolve(monkeypatch, target: Path, answer: str) -> None:
    original = Path.resolve

    def resolve(self, strict=False):
        return Path(answer) if self == target else original(self, strict=strict)

    monkeypatch.setattr(Path, 'resolve', resolve)


@pytest.mark.skipif(os.name != 'nt', reason='the extended-length spelling exists only on Windows')
def test_a_directory_resolved_with_the_prefix_is_still_its_own_path(tmp_path, monkeypatch):
    target = tmp_path / 'task'
    _prefixing_resolve(monkeypatch, target, EXTENDED + str(target))
    assert path_identity.resolved(target) == target
    _directory(target)


@pytest.mark.skipif(os.name != 'nt', reason='the extended-length spelling exists only on Windows')
def test_a_prefixed_resolution_to_another_place_is_still_refused(tmp_path, monkeypatch):
    target = tmp_path / 'task'
    _prefixing_resolve(monkeypatch, target, EXTENDED + str(tmp_path / 'elsewhere'))
    with pytest.raises(AgentTaskError, match='escapes its owner cache'):
        _directory(target)


def test_other_platforms_compare_against_resolve_unchanged(tmp_path, monkeypatch):
    target = tmp_path / 'task'
    monkeypatch.setattr(path_identity.os, 'name', 'posix')
    assert path_identity.resolved(target) == target.resolve()
