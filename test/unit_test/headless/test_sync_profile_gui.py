"""Offscreen native loading keeps engines and windows unchanged until explicit owner-bound editor actions."""
import json
import os
from pathlib import Path
from threading import Event, get_ident

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QLabel

from headless.test_config_sync_gui import idle, run
from headless.test_sync_profile_load import materialized
import je_auto_control as ac
from je_auto_control.gui import config_sync_worker, main_widget
from je_auto_control.gui.config_sync_worker import ConfigSyncWorker, SyncUIRequest
from je_auto_control.gui.main_window import AutoControlGUIUI
from je_auto_control.gui.script_builder.step_model import steps_to_actions
from je_auto_control.utils.rbac import AuthorizationContext, Role, UserStore, authorization_scope


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    monkeypatch.setattr(main_widget, 'TAB_SPECS', tuple(
        spec for spec in main_widget.TAB_SPECS if spec.key in {'config_sync', 'script_builder'}))
    settings = QSettings(str(tmp_path / 'current.ini'), QSettings.Format.IniFormat)
    view = AutoControlGUIUI(settings=settings)
    yield view
    panel = view.auto_control_gui_widget.tab_registry.open('config_sync')
    panel.cancel()
    if panel._handle is not None:
        assert panel._handle.wait(5)
    view.close()
    view.deleteLater()
    app.processEvents()


def prepare(view, tmp_path):
    result = materialized(tmp_path)
    panel = view.auto_control_gui_widget.tab_registry.open('config_sync')
    panel._generation_directory.setText(result['directory'])
    panel._manifest_digest.setText(result['manifest_digest'])
    panel._working_root.setText(str(tmp_path / 'workspaces'))
    return panel, result


def test_native_load_runs_in_worker_without_configuration_and_opens_only_by_explicit_actions(window, app,
                                                                                           tmp_path, monkeypatch):
    panel, result = prepare(window, tmp_path)
    assert not panel._configuration.toPlainText()
    current_thread = get_ident()
    threads = []
    load = config_sync_worker.load_sync_profile

    def loaded(*args, **kwargs):
        threads.append(get_ident())
        return load(*args, **kwargs)

    monkeypatch.setattr(config_sync_worker, 'load_sync_profile', loaded)
    monkeypatch.setattr(ac.HotkeyDaemon, 'start', lambda *_a, **_k: pytest.fail('load started a hotkey backend'))
    monkeypatch.setattr(ac.TriggerEngine, 'start', lambda *_a, **_k: pytest.fail('load armed a trigger engine'))
    monkeypatch.setattr(ac.executor, '_execute_event', lambda *_a, **_k: pytest.fail('load/import executed actions'))
    original = (Path(result['directory']) / 'workspace.ini').read_bytes()
    panel.begin('load_profile')
    idle(app, panel)
    assert panel._status_key == 'done', panel._status.text()
    profile = panel._native_profile
    assert isinstance(profile, ac.LoadedSyncProfile) and threads and all(item != current_thread for item in threads)
    assert profile.hotkeys[0].enabled is False and profile.triggers[0].enabled is False
    panel._kind.setCurrentText('hotkeys')
    panel._inspect_loaded()
    assert json.loads(panel._details.toPlainText())['definitions']['demo-key']['enabled'] is False
    assert window._theme_name == 'dark' and window._user_font_pt == 0
    builder = window.auto_control_gui_widget.tab_registry.open('script_builder')
    with authorization_scope(AuthorizationContext('viewer', Role.VIEWER)):
        panel._open_loaded_script()
        assert panel._status_key == 'error'
        panel._apply_loaded_preferences()
        assert panel._status_key == 'error' and window._theme_name == 'dark'
    assert steps_to_actions(builder._tree.root_steps()) == []
    window.auto_control_gui_widget.activate_tab('script_builder')
    window.auto_control_gui_widget.activate_tab('config_sync')
    panel._open_loaded_script()
    assert panel._status_key == 'script_opened', panel._status.text()
    assert window.auto_control_gui_widget.tabs.currentWidget() is builder
    assert steps_to_actions(builder._tree.root_steps()) == profile.script_actions('demo.json')
    assert builder._source_path == str(profile.scripts['demo.json'])
    assert window._theme_name == 'dark'
    panel._apply_loaded_preferences()
    assert panel._status_key == 'loaded_preferences_applied' and window._theme_name == 'light'
    assert (Path(result['directory']) / 'workspace.ini').read_bytes() == original
    assert panel._last_sync is None


def test_revoked_loaded_profile_owner_cannot_import_scripts_or_apply_preferences(window, app, tmp_path, monkeypatch):
    panel, _ = prepare(window, tmp_path)
    store = UserStore(tmp_path / 'users.json')
    store.add_user(user_id='owner', display_name='Owner', role=Role.OPERATOR)
    with authorization_scope(AuthorizationContext('owner', Role.OPERATOR, store_path=str(store.path))):
        panel.begin('load_profile')
    idle(app, panel)
    assert panel._native_profile is not None and panel._status_key == 'done'
    store.set_role('owner', Role.VIEWER)
    monkeypatch.setattr(window, 'import_sync_script', lambda *_a: pytest.fail('revoked editor import'))
    monkeypatch.setattr(window, 'apply_workspace_preferences', lambda *_a: pytest.fail('revoked GUI preferences'))
    panel._open_loaded_script()
    assert panel._status_key == 'error'
    panel._apply_loaded_preferences()
    assert panel._status_key == 'error' and window._theme_name == 'dark'


def test_cancel_before_copy_and_close_before_delivery_never_attach_delayed_profiles(window, app, tmp_path, monkeypatch):
    panel, result = prepare(window, tmp_path)
    entered, release = Event(), Event()
    load = config_sync_worker.load_sync_profile

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return load(*args, **kwargs)

    monkeypatch.setattr(config_sync_worker, 'load_sync_profile', delayed)
    panel.begin('load_profile')
    assert entered.wait(5)
    panel.cancel()
    release.set()
    idle(app, panel)
    assert panel._native_profile is None and panel._status_key == 'cancelled'
    assert not (tmp_path / 'workspaces').exists()
    committed = load(result['directory'], tmp_path / 'workspaces', expected_digest=result['manifest_digest'])
    entered.clear()
    release.clear()

    def completed(*_args, **_kwargs):
        entered.set()
        assert release.wait(5)
        return committed

    monkeypatch.setattr(config_sync_worker, 'load_sync_profile', completed)
    panel.begin('load_profile')
    assert entered.wait(5)
    panel.close()
    release.set()
    idle(app, panel)
    assert panel._native_profile is None and committed.directory.is_dir()


def test_worker_keeps_committed_native_load_success_after_a_late_stop(app, tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    result = materialized(tmp_path)
    options = {'directory': result['directory'], 'target_root': str(tmp_path / 'workspaces'),
               'expected_digest': result['manifest_digest']}
    worker = ConfigSyncWorker(SyncUIRequest(1, 'load_profile', '', json.dumps(options)))
    load = config_sync_worker.load_sync_profile

    def committed(*args, **kwargs):
        profile = load(*args, **kwargs)
        worker.request_stop()
        return profile

    monkeypatch.setattr(config_sync_worker, 'load_sync_profile', committed)
    try:
        outcome = run(worker)
        assert outcome.status == 'ok' and outcome.profile.directory.is_dir()
        assert outcome.profile.hotkeys[0].enabled is False
    finally:
        worker.deleteLater()


@pytest.mark.parametrize('command,parameters', [('AC_<b>literal</b>', {}),
                                             ('AC_click_mouse', ['<b>literal</b>'])])
def test_imported_script_names_and_positional_values_render_as_literal_text(window, app, command, parameters):
    window.import_sync_script([[command, parameters]], '<loaded-snapshot>')
    builder = window.auto_control_gui_widget.tab_registry.open('script_builder')
    builder._form.load_step(builder._tree.root_steps()[0])
    if isinstance(parameters, dict):
        label = builder._form._title
        expected = 'Unknown command: ' + command
    else:
        expected = repr(parameters)
        label = next(item for item in builder._form.findChildren(QLabel) if item.text() == expected)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    window.show()
    app.processEvents()
    label.setSelection(0, len(expected))
    assert label.selectedText() == expected
