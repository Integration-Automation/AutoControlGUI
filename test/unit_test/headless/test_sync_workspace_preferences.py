"""Native GUI preferences bridge to causal profiles without Qt in the capture path or implicit activation."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

import je_auto_control as ac


def adapter(tmp_path, origin):
    identity = ac.SyncLocalIdentity('https://controlled.invalid', 'alice', origin)
    return ac.WorkspaceSettingsSyncAdapter(tmp_path / (origin + '.ini'),
        ac.SyncAdapterState(tmp_path / (origin + '.sqlite3'), identity))


def test_native_preference_capture_excludes_other_settings_and_materializes_a_complete_inert_ini(tmp_path):
    source = tmp_path / 'desktop.ini'
    original = ('[workspace]\ntheme=light\nfont_pt=16\nnavigation_visible=false\nnavigation_width=480\n'
                '\n[private]\npassword=local-only-credential\n\n[geometry]\nmonitor=sender-display\n')
    source.write_text(original, encoding='utf-8')
    sender, receiver = adapter(tmp_path, 'desktop'), adapter(tmp_path, 'laptop')
    entries = sender.snapshot()
    assert {entry.entry_id for entry in entries.values()} == {
        'theme', 'font_pt', 'navigation_visible', 'navigation_width'}
    assert {entry.section for entry in entries.values()} == {'workspace'}
    assert receiver.apply(entries).stored == ('font_pt', 'navigation_visible', 'navigation_width', 'theme')
    result = ac.materialize_sync_profile([receiver], tmp_path / 'cache')
    assert '[workspace]' in (result.directory / 'workspace.ini').read_text(encoding='utf-8')
    assert source.read_text(encoding='utf-8') == original and not (tmp_path / 'laptop.ini').exists()
    stored = (tmp_path / 'desktop.sqlite3', tmp_path / 'laptop.sqlite3', result.directory / 'profile/workspace.json')
    for path in stored:
        assert b'local-only-credential' not in path.read_bytes() and b'sender-display' not in path.read_bytes()
    assert adapter(tmp_path, 'desktop').snapshot() == entries


def test_preferences_keep_parallel_edits_and_exact_reviewed_resolution(tmp_path):
    left, right = adapter(tmp_path, 'desktop'), adapter(tmp_path, 'laptop')
    (tmp_path / 'desktop.ini').write_text('[workspace]\ntheme=light\n', encoding='utf-8')
    (tmp_path / 'laptop.ini').write_text('[workspace]\ntheme=dark\n', encoding='utf-8')
    assert right.apply(left.snapshot()).conflicts == ('theme',)
    with pytest.raises(ac.ConfigSyncError):
        ac.materialize_sync_profile([right], tmp_path / 'cache')
    right.resolve('theme', {'value': 'light'}, observed=tuple(right.snapshot()))
    assert right.definitions() == {'theme': {'value': 'light'}}
    assert (tmp_path / 'laptop.ini').read_text(encoding='utf-8') == '[workspace]\ntheme=dark\n'


@pytest.mark.parametrize(('name', 'value'), [('geometry', 'sender-window'), ('theme', 'unknown'),
    ('font_pt', True), ('font_pt', 13), ('navigation_visible', 'false'), ('navigation_width', 10 ** 400)])
def test_incoming_preferences_require_known_keys_and_native_types_before_state(tmp_path, name, value):
    receiver = adapter(tmp_path, 'laptop')
    entry = ac.SyncEntry('workspace', name, {'value': value}, {'desktop': 1}, 'edit', 'desktop')
    with pytest.raises(ac.ConfigSyncError):
        receiver.apply({entry.change_id: entry})
    assert not (tmp_path / 'laptop.sqlite3').exists()


def test_corrupt_or_oversized_native_ini_is_refused_without_state(tmp_path):
    receiver = adapter(tmp_path, 'desktop')
    for content in ('[workspace\ntheme=light', 'x' * (1024 * 1024 + 1)):
        (tmp_path / 'desktop.ini').write_text(content, encoding='utf-8')
        with pytest.raises(ac.ConfigSyncError):
            receiver.snapshot()
        assert not (tmp_path / 'desktop.sqlite3').exists()


def test_native_ini_errors_do_not_include_private_source_lines(tmp_path):
    import traceback
    (tmp_path / 'desktop.ini').write_text('private-credential-in-a-malformed-source\n', encoding='utf-8')
    with pytest.raises(ac.ConfigSyncError) as caught:
        adapter(tmp_path, 'desktop').snapshot()
    assert 'private-credential-in-a-malformed-source' not in ''.join(traceback.format_exception(caught.value))


def test_ini_default_sections_do_not_inject_preferences(tmp_path):
    (tmp_path / 'desktop.ini').write_text('[DEFAULT]\ntheme=light\n\n[workspace]\nfont_pt="16"\n', encoding='utf-8')
    entries = adapter(tmp_path, 'desktop').snapshot()
    assert {entry.entry_id: entry.value for entry in entries.values()} == {'font_pt': {'value': 16}}


def test_native_group_and_key_case_matches_the_local_qsettings_reader(tmp_path):
    core = pytest.importorskip('PySide6.QtCore', exc_type=ImportError)
    source = tmp_path / 'desktop.ini'
    source.write_text('[Workspace]\nTheme=light\n', encoding='utf-8')
    native = core.QSettings(str(source), core.QSettings.Format.IniFormat)
    expected = {'theme': {'value': 'light'}} if native.contains('workspace/theme') else {}
    entries = adapter(tmp_path, 'desktop').snapshot()
    assert {entry.entry_id: entry.value for entry in entries.values()} == expected


def test_preference_tombstone_resets_only_the_inert_native_profile_to_its_default(tmp_path):
    source = tmp_path / 'desktop.ini'
    source.write_text('[workspace]\ntheme=light\n', encoding='utf-8')
    sender, receiver = adapter(tmp_path, 'desktop'), adapter(tmp_path, 'laptop')
    receiver.apply(sender.snapshot())
    source.write_text('[workspace]\n', encoding='utf-8')
    tombstones = sender.snapshot()
    assert next(iter(tombstones.values())).is_deleted
    receiver.apply(tombstones)
    result = ac.materialize_sync_profile([receiver], tmp_path / 'cache')
    assert 'theme=dark' in (result.directory / 'workspace.ini').read_text(encoding='utf-8')
    assert not (tmp_path / 'laptop.ini').exists()


def test_materialized_ini_loads_in_a_fresh_real_gui_without_changing_the_current_preferences(tmp_path, monkeypatch):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    core = pytest.importorskip('PySide6.QtCore', exc_type=ImportError)
    widgets = pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
    from je_auto_control.gui import main_widget
    from je_auto_control.gui.main_window import AutoControlGUIUI
    from je_auto_control.gui.workspace_settings import WorkspacePreferences

    app = widgets.QApplication.instance() or widgets.QApplication([])
    native = core.QSettings(str(tmp_path / 'desktop.ini'), core.QSettings.Format.IniFormat)
    for name, value in {'theme': 'light', 'font_pt': 16, 'navigation_visible': False, 'navigation_width': 480}.items():
        native.setValue('workspace/' + name, value)
    native.setValue('private/token', 'do-not-sync')
    native.sync()
    expected = WorkspacePreferences.load(native)
    receiver = adapter(tmp_path, 'laptop')
    receiver.apply(adapter(tmp_path, 'desktop').snapshot())
    result = ac.materialize_sync_profile([receiver], tmp_path / 'cache')
    generated = (result.directory / 'workspace.ini').read_bytes()
    working_copy = tmp_path / 'explicit-workspace.ini'
    working_copy.write_bytes(generated)
    settings = core.QSettings(str(working_copy), core.QSettings.Format.IniFormat)
    assert WorkspacePreferences.load(settings) == expected
    monkeypatch.setattr(main_widget, 'TAB_SPECS', tuple(
        spec for spec in main_widget.TAB_SPECS if spec.key in {'record', 'variables'}))
    window = AutoControlGUIUI(settings=settings)
    try:
        assert window._theme_name == 'light' and window._user_font_pt == 16
        assert window._navigation_dock.isHidden() and window._navigation_width == 480
        assert not (tmp_path / 'laptop.ini').exists()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
    assert (result.directory / 'workspace.ini').read_bytes() == generated


def test_workspace_descriptor_commands_and_all_seven_domains_publish_together(tmp_path, monkeypatch):
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.gui.script_builder.step_model import action_to_step, step_to_action

    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    kinds = ('scripts', 'locators', 'hotkeys', 'triggers', 'address_book', 'settings', 'workspace')
    profiles = [{'schema_version': 1, 'kind': kind, 'state_path': str(tmp_path / 'profiles.sqlite3'),
                 'identity': {'endpoint': 'https://controlled.invalid', 'user_id': 'alice', 'origin': 'desktop'},
                 'source': {'records': {}}} for kind in kinds]
    command = ['AC_sync_profile_materialize', {'profiles': profiles, 'target_root': str(tmp_path / 'cache')}]
    assert step_to_action(action_to_step(command)) == command
    ac.executor.execute_action([command], raise_on_error=True)
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    result = tools['ac_sync_profile_materialize'].handler(**command[1])
    assert result['reused'] and result['file_count'] == 13
    assert (Path(result['directory']) / 'workspace.ini').is_file()
    source = tmp_path / 'gui.ini'
    source.write_text('[workspace]\ntheme=light\n', encoding='utf-8')
    workspace = dict(profiles[-1], source={'path': str(source)})
    captured = tools['ac_sync_adapter_snapshot'].handler(workspace)
    assert next(iter(captured['entries'].values()))['value'] == {'value': 'light'}


def test_native_workspace_capture_is_qt_free_in_a_fresh_process(tmp_path):
    source = tmp_path / 'gui.ini'
    source.write_text('[workspace]\ntheme=light\n', encoding='utf-8')
    script = ('import sys,je_auto_control as ac; '
              'identity=ac.SyncLocalIdentity("https://controlled.invalid","alice","desktop"); '
              's=ac.SyncAdapterState(sys.argv[2],identity); '
              'a=ac.WorkspaceSettingsSyncAdapter(sys.argv[1],s); assert len(a.snapshot())==1; '
              'assert not any(x.startswith("PySide6") for x in sys.modules)')
    result = subprocess.run([sys.executable, '-c', script, str(source), str(tmp_path / 'state.sqlite3')],
                            capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
