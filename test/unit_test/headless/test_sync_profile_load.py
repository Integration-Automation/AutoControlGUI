"""Explicit native loading creates independent mutable working copies with every runtime definition disabled."""
from concurrent.futures import CancelledError
from pathlib import Path

import pytest

import je_auto_control as ac
from je_auto_control.utils.config_sync.adapter_commands import _materialize_sync_profile
from je_auto_control.utils.config_sync.adapter_factory import adapter_from_profile


def profiles(tmp_path):
    records = {
        'scripts': {'demo.json': {'actions': [['AC_log', {'message': 'loaded but never executed'}]]}},
        'locators': {'login': {'name': 'Sign in', 'role': 'button'}},
        'hotkeys': {'demo-key': {'combo': 'ctrl+alt+1', 'script_path': 'scripts/demo.json'}},
        'triggers': {'demo-trigger': {'kind': 'all', 'script_path': 'scripts/demo.json', 'repeat': True,
            'cooldown_seconds': 1, 'children': [{'kind': 'file', 'script_path': '', 'repeat': False,
                'cooldown_seconds': 0, 'condition': {'watch_path': 'assets/watched.txt'}}]}},
        'address_book': {}, 'settings': {'example': {'value': 'local working value'}},
        'workspace': {'theme': {'value': 'light'}},
    }
    return [{'schema_version': 1, 'kind': kind, 'state_path': str(tmp_path / 'adapters.sqlite3'),
             'identity': {'endpoint': 'https://controlled.invalid', 'user_id': 'alice', 'origin': 'desktop'},
             'source': {'records': entries}} for kind, entries in records.items()]


def materialized(tmp_path):
    selected = profiles(tmp_path)
    for profile in selected:
        adapter_from_profile(profile).snapshot()
    return _materialize_sync_profile(selected, str(tmp_path / 'cache'))


def test_load_constructs_real_native_definitions_in_an_independent_editable_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    result = materialized(tmp_path)
    generation = Path(result['directory'])
    before = {path.relative_to(generation).as_posix(): path.read_bytes()
              for path in generation.rglob('*') if path.is_file()}
    original_hotkeys = ac.default_hotkey_daemon.list_bindings()
    original_triggers = ac.default_trigger_engine.list_triggers()
    monkeypatch.setattr(ac.executor, 'execute_action', lambda *_a, **_k: pytest.fail('loading executed actions'))
    monkeypatch.setattr(ac.HotkeyDaemon, 'start', lambda *_a, **_k: pytest.fail('loading started hotkeys'))
    monkeypatch.setattr(ac.TriggerEngine, 'start', lambda *_a, **_k: pytest.fail('loading started triggers'))
    loaded = ac.load_sync_profile(generation, tmp_path / 'workspaces', expected_digest=result['manifest_digest'])
    assert isinstance(loaded, ac.LoadedSyncProfile)
    assert loaded.directory.is_relative_to(tmp_path / 'workspaces')
    assert loaded.directory != generation and loaded.manifest_digest == result['manifest_digest']
    assert loaded.script_actions('demo.json') == [['AC_log', {'message': 'loaded but never executed'}]]
    assert loaded.scripts['demo.json'] == loaded.directory / 'scripts/demo.json'
    assert loaded.locators.all()['login'] == {'name': 'Sign in', 'role': 'button'}
    assert loaded.address_book.list_entries() == []
    assert isinstance(loaded.hotkeys[0], ac.HotkeyBinding) and loaded.hotkeys[0].enabled is False
    assert loaded.hotkeys[0].script_path == str(loaded.directory / 'scripts/demo.json')
    assert isinstance(loaded.triggers[0], ac.AllOfTrigger) and loaded.triggers[0].enabled is False
    assert loaded.triggers[0].children[0].enabled is False
    assert loaded.preferences == {'theme': 'light', 'font_pt': 0, 'navigation_visible': True, 'navigation_width': 260}
    assert loaded.settings == {'example': 'local working value'}
    loaded.locators.save('cancel', name='Cancel')
    assert 'cancel' in loaded.locators.all()
    assert ac.default_hotkey_daemon.list_bindings() == original_hotkeys
    assert ac.default_trigger_engine.list_triggers() == original_triggers
    assert {path.relative_to(generation).as_posix(): path.read_bytes()
            for path in generation.rglob('*') if path.is_file()} == before


def test_two_explicit_loads_never_share_mutable_native_files(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    result = materialized(tmp_path)
    first = ac.load_sync_profile(result['directory'], tmp_path / 'workspaces',
                                 expected_digest=result['manifest_digest'])
    second = ac.load_sync_profile(result['directory'], tmp_path / 'workspaces',
                                  expected_digest=result['manifest_digest'])
    assert first.directory != second.directory
    first.locators.save('new', name='New')
    assert 'new' not in second.locators.all()
    assert all(not binding.enabled for binding in (*first.hotkeys, *second.hotkeys))


@pytest.mark.parametrize('digest', ['', 'wrong', 'A' * 64, None, 1])
def test_invalid_review_digest_fails_before_creating_any_working_directory(tmp_path, monkeypatch, digest):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    with pytest.raises(ac.ConfigSyncError):
        ac.load_sync_profile(tmp_path / 'absent', tmp_path / 'workspaces', expected_digest=digest)
    assert not (tmp_path / 'workspaces').exists()


def test_changed_or_corrupt_generation_never_creates_a_loaded_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    result = materialized(tmp_path)
    with pytest.raises(ac.ConfigSyncError):
        ac.load_sync_profile(result['directory'], tmp_path / 'workspaces', expected_digest='0' * 64)
    target = Path(result['directory']) / 'scripts/demo.json'
    target.write_text('[]', encoding='utf-8')
    with pytest.raises(ac.ConfigSyncError):
        ac.load_sync_profile(result['directory'], tmp_path / 'workspaces', expected_digest=result['manifest_digest'])
    assert not list((tmp_path / 'workspaces').glob('workspace-*')) if (tmp_path / 'workspaces').exists() else True


def test_cancelled_load_cannot_publish_a_partial_working_copy(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    result = materialized(tmp_path)
    with pytest.raises(CancelledError):
        ac.load_sync_profile(result['directory'], tmp_path / 'workspaces',
                             expected_digest=result['manifest_digest'], cancelled=lambda: True)
    assert not (tmp_path / 'workspaces').exists()


@pytest.mark.parametrize('kind,condition,expected', [
    ('file', {'watch_path': 'assets/watched.txt'}, ac.FilePathTrigger),
    ('image', {'image_path': 'assets/template.png', 'threshold': 0.8}, ac.ImageAppearsTrigger),
    ('window', {'title_substring': 'Example', 'case_sensitive': False}, ac.WindowAppearsTrigger),
    ('pixel', {'x': 1, 'y': 2, 'target_rgb': [1, 2, 3], 'tolerance': 4}, ac.PixelColorTrigger),
    ('cron', {'cron': '* * * * *'}, ac.CronTrigger),
    ('all', {}, ac.AllOfTrigger), ('any', {}, ac.AnyOfTrigger), ('sequence', {}, ac.SequenceTrigger),
])
def test_every_supported_native_trigger_kind_loads_disabled_without_polling(tmp_path, monkeypatch,
                                                                         kind, condition, expected):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    profile = profiles(tmp_path)[3]
    value = {'kind': kind, 'script_path': 'scripts/demo.json', 'repeat': True, 'cooldown_seconds': 1}
    if kind in {'all', 'any', 'sequence'}:
        value['children'] = [{'kind': 'file', 'script_path': '', 'repeat': False, 'cooldown_seconds': 0,
                              'condition': {'watch_path': 'assets/watched.txt'}}]
    else:
        value['condition'] = condition
    profile['source']['records'] = {'native': value}
    adapter_from_profile(profile).snapshot()
    result = _materialize_sync_profile([profile], str(tmp_path / 'cache'))
    loaded = ac.load_sync_profile(result['directory'], tmp_path / 'workspaces',
                                  expected_digest=result['manifest_digest'])
    trigger = loaded.triggers[0]
    assert isinstance(trigger, expected) and trigger.enabled is False
    assert trigger.script_path == str(loaded.directory / 'scripts/demo.json')
    if hasattr(trigger, 'children'):
        assert all(child.enabled is False for child in trigger.children)
