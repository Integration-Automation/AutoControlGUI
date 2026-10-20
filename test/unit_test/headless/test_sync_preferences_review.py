"""Explicit preference application binds the exact reviewed native heads without source/network/credential reads."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.config_sync.adapter_commands import _apply_sync_adapter
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry


def configuration(tmp_path):
    return {'schema_version': 1, 'endpoint': 'https://controlled.invalid', 'user_id': 'alice',
            'outbox_path': str(tmp_path / 'outbox.sqlite3'), 'profiles': [
                {'kind': 'workspace', 'state_path': str(tmp_path / 'state.sqlite3'), 'source': {'records': {}}}]}


def apply(tmp_path, config, entries):
    identity = ac.SyncOutbox(tmp_path / 'outbox.sqlite3').identity(config['endpoint'], 'alice')
    profile = dict(config['profiles'][0], schema_version=1, identity={
        'endpoint': identity.endpoint, 'user_id': identity.user_id, 'origin': identity.origin})
    return _apply_sync_adapter(profile, {entry.change_id: entry.to_dict() for entry in entries})


def test_preferences_return_only_canonical_reviewed_values_and_safe_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    config = configuration(tmp_path)
    entries = [ac.SyncEntry('workspace', name, {'value': value}, {'desktop': 1}, name, 'desktop')
               for name, value in [('theme', 'light'), ('font_pt', 16), ('navigation_visible', False)]]
    apply(tmp_path, config, entries)
    workspace = ac.SyncWorkspace(config)
    heads = workspace.review('workspace')
    assert workspace.preferences(observed=heads) == {'theme': 'light', 'font_pt': 16,
        'navigation_visible': False, 'navigation_width': 260}
    tombstone = entries[1].evolve({}, origin='desktop', operation_id='remove-font', is_deleted=True)
    apply(tmp_path, config, [tombstone])
    heads = workspace.review('workspace')
    assert workspace.preferences(observed=heads)['font_pt'] == 0


def test_stale_or_conflicting_review_never_selects_a_preference_winner(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    config = configuration(tmp_path)
    original = ac.SyncEntry('workspace', 'theme', {'value': 'light'}, {'desktop': 1}, 'first', 'desktop')
    apply(tmp_path, config, [original])
    workspace = ac.SyncWorkspace(config)
    reviewed = workspace.review('workspace')
    parallel = ac.SyncEntry('workspace', 'theme', {'value': 'dark'}, {'laptop': 1}, 'parallel', 'laptop')
    apply(tmp_path, config, [parallel])
    with pytest.raises(ac.ConfigSyncError, match='changed'):
        workspace.preferences(observed=reviewed)
    with pytest.raises(ac.ConfigSyncError, match='conflict'):
        workspace.preferences(observed=workspace.review('workspace'))


def test_preferences_ac_mcp_builder_share_exact_review_and_do_not_read_sources(tmp_path, monkeypatch):
    from je_auto_control.gui.script_builder.step_model import action_to_step, step_to_action
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    config = configuration(tmp_path)
    entry = ac.SyncEntry('workspace', 'theme', {'value': 'light'}, {'desktop': 1}, 'theme', 'desktop')
    apply(tmp_path, config, [entry])
    source = tmp_path / 'private.ini'
    source.write_text('invalid-source-that-must-not-be-read', encoding='utf-8')
    config['profiles'][0]['source'] = {'path': str(source)}
    action = ['AC_sync_workspace', {'configuration': config, 'operation': 'preferences',
                                     'options': {'observed': [entry.change_id]}}]
    assert step_to_action(action_to_step(action)) == action
    ac.executor.execute_action([action], raise_on_error=True)
    tool = next(item for item in build_default_tool_registry() if item.name == 'ac_sync_workspace')
    assert tool.handler(**action[1])['theme'] == 'light'


@pytest.mark.parametrize('observed', [None, 'one', [False], ['x'] * 1025])
def test_preferences_refuse_malformed_review_before_opening_storage(tmp_path, monkeypatch, observed):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    tool = next(item for item in build_default_tool_registry() if item.name == 'ac_sync_workspace')
    with pytest.raises(ac.ConfigSyncError):
        tool.handler(configuration(tmp_path), 'preferences', {'observed': observed})
    assert not list(tmp_path.glob('*.sqlite3'))
