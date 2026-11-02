"""Offscreen Sync actions keep reviewed data inert, authority live and worker results bound to their view."""
from concurrent.futures import CancelledError
from contextvars import ContextVar
import json
import os
from threading import Event, get_ident
import time

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QPushButton

from headless.test_sync_preferences_review import apply, configuration
import je_auto_control as ac
from je_auto_control.gui import config_sync_worker, main_widget
from je_auto_control.gui.config_sync_tab import ConfigSyncTab
from je_auto_control.gui.config_sync_worker import ConfigSyncWorker, SyncUIRequest
from je_auto_control.gui.main_window import AutoControlGUIUI
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac import AuthorizationContext, Role, UserStore, authorization_scope


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(app, tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    view = ConfigSyncTab()
    yield view
    view.cancel()
    if view._handle is not None:
        assert view._handle.wait(5)
    view.deleteLater()
    app.processEvents()


def idle(app, view):
    deadline = time.monotonic() + 10
    while view._handle is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert view._handle is None


def run(worker):
    results = []
    worker.finished.connect(results.append)
    worker.run()
    assert len(results) == 1
    return results[0]


def test_constructing_sync_is_inert_and_local_actions_run_off_the_gui_thread(panel, app, tmp_path, monkeypatch):
    assert not list(tmp_path.iterdir()) and panel.findChildren(QPushButton) == []
    assert len(panel.menu_actions()) == 17
    config = configuration(tmp_path)
    panel._configuration.setPlainText(json.dumps(config))
    gui_thread = get_ident()
    operation = config_sync_worker._sync_workspace
    threads = []

    def invoke(*args, **kwargs):
        threads.append(get_ident())
        return operation(*args, **kwargs)

    monkeypatch.setattr(config_sync_worker, '_sync_workspace', invoke)
    panel.begin('capture')
    idle(app, panel)
    panel.begin('status')
    idle(app, panel)
    assert threads and all(thread != gui_thread for thread in threads)
    assert panel._status_key == 'done' and panel._last_sync is None
    assert panel._reviewed is None


def test_review_selection_resolves_all_heads_and_configuration_change_discards_review(panel, app, tmp_path):
    config = configuration(tmp_path)
    heads = [ac.SyncEntry('workspace', 'theme', {'value': value}, {origin: 1}, origin, origin)
             for origin, value in [('desktop', 'light'), ('laptop', 'dark')]]
    apply(tmp_path, config, heads)
    panel._configuration.setPlainText(json.dumps(config))
    panel._kind.setCurrentText('workspace')
    panel.begin('preferences')
    assert panel._handle is None and panel._status_key == 'error'
    panel.begin('review')
    idle(app, panel)
    assert panel._heads.rowCount() == 2
    assert set(panel._resolution_options()['observed']) == {head.change_id for head in heads}
    panel._value.setPlainText('{"value":"light"}')
    panel.begin('resolve')
    idle(app, panel)
    assert panel._status_key == 'done' and panel._reviewed is None
    assert len(ac.SyncWorkspace(config).review('workspace')) == 1
    panel.begin('review')
    idle(app, panel)
    panel._configuration.setPlainText('{}')
    assert panel._reviewed is None and panel._heads.rowCount() == 0
    assert not panel._value.toPlainText()


def test_loopback_sync_does_not_apply_preferences_until_explicit_reviewed_action(app, tmp_path, monkeypatch):
    from examples.causal_peer_control import loopback_server
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    monkeypatch.setattr(main_widget, 'TAB_SPECS', tuple(
        spec for spec in main_widget.TAB_SPECS if spec.key == 'config_sync'))
    settings = QSettings(str(tmp_path / 'current.ini'), QSettings.Format.IniFormat)
    settings.setValue('private/token', 'keep-local')
    settings.sync()
    window = AutoControlGUIUI(settings=settings)
    window.auto_control_gui_widget.show_tab('config_sync')
    view = window.auto_control_gui_widget.tab_registry.open('config_sync')
    try:
        with loopback_server(ac.CausalConfigStore(tmp_path / 'server.sqlite3')) as endpoint:
            config = configuration(tmp_path)
            config.update(endpoint=endpoint, user_id='example')
            config['profiles'][0]['source'] = {'records': {'theme': {'value': 'light'},
                'font_pt': {'value': 16}, 'navigation_visible': {'value': False},
                'navigation_width': {'value': 440}}}
            view._configuration.setPlainText(json.dumps(config))
            for operation in ('register', 'sync'):
                view.begin(operation)
                idle(app, view)
                assert view._status_key == 'done', view._status.text()
            assert view._last_sync is not None
            successful_revision = view._last_sync
            assert window._theme_name == 'dark' and window._user_font_pt == 0
            view._kind.setCurrentText('workspace')
            assert view._last_sync == successful_revision
            view.begin('review')
            idle(app, view)
            assert view._heads.rowCount() == 4 and window._theme_name == 'dark'
            view.begin('preferences')
            idle(app, view)
            assert view._status_key == 'applied', view._status.text()
            assert window._theme_name == 'light' and window._user_font_pt == 16
            assert window._navigation_dock.isHidden() and window._navigation_width == 440
            assert settings.value('private/token') == 'keep-local'
            assert settings.value('workspace/theme') is None
    finally:
        view.cancel()
        if view._handle is not None:
            view._handle.wait(5)
        window.close()
        window.deleteLater()
        app.processEvents()
    assert settings.value('workspace/theme') == 'light'


def test_live_preferences_validate_every_value_before_mutating_the_window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(main_widget, 'TAB_SPECS', ())
    window = AutoControlGUIUI(settings=QSettings(str(tmp_path / 'current.ini'), QSettings.Format.IniFormat))
    try:
        with pytest.raises(ac.ConfigSyncError):
            window.apply_workspace_preferences({'theme': 'light', 'font_pt': True,
                'navigation_visible': False, 'navigation_width': 440})
        assert window._theme_name == 'dark' and window._user_font_pt == 0
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_cancelled_or_closed_view_discards_delayed_preference_application(panel, app, monkeypatch):
    entered, release = Event(), Event()
    applied = []

    def delayed(*_args, **_kwargs):
        entered.set()
        assert release.wait(5)
        return {'theme': 'light', 'font_pt': 16, 'navigation_visible': False, 'navigation_width': 440}

    monkeypatch.setattr(config_sync_worker, '_sync_workspace', delayed)
    monkeypatch.setattr(panel, '_apply_result', lambda outcome: applied.append(outcome))
    panel._configuration.setPlainText('{}')
    panel._kind.setCurrentText('workspace')
    panel._reviewed = {}
    panel.begin('preferences')
    assert entered.wait(5)
    panel.cancel()
    release.set()
    idle(app, panel)
    assert applied == [] and panel._status_key == 'cancelled'
    release.clear()
    entered.clear()
    panel.begin('preferences')
    assert entered.wait(5)
    panel.close()
    release.set()
    idle(app, panel)
    assert applied == []


def test_worker_captures_context_preserves_committed_success_and_cancels_late_delivery(app, monkeypatch):
    context = ContextVar('sync_ui_test', default='ambient')
    context.set('registrant')
    worker = ConfigSyncWorker(SyncUIRequest(1, 'capture', '{}'))
    context.set('different')

    def committed(*_args, **_kwargs):
        assert context.get() == 'registrant'
        worker.request_stop()
        return {'captured': 1}

    monkeypatch.setattr(config_sync_worker, '_sync_workspace', committed)
    try:
        assert run(worker).status == 'ok'
        with pytest.raises(CancelledError):
            worker.deliver(lambda: pytest.fail('stopped preferences must not be delivered'), require_active=True)
        delivered = []
        worker.deliver(lambda: delivered.append(context.get()))
        assert delivered == ['registrant']
    finally:
        worker.deleteLater()


def test_viewer_and_pre_cancelled_workers_do_not_enter_core(app, monkeypatch):
    monkeypatch.setattr(config_sync_worker, '_sync_workspace', lambda *_a, **_k: pytest.fail('unauthorised I/O'))
    with authorization_scope(AuthorizationContext('viewer', Role.VIEWER)):
        viewer = ConfigSyncWorker(SyncUIRequest(1, 'status', '{}'))
    stopped = ConfigSyncWorker(SyncUIRequest(2, 'capture', '{}'))
    stopped.request_stop()
    try:
        assert run(viewer).status == 'error'
        assert run(stopped).status == 'cancelled'
    finally:
        viewer.deleteLater()
        stopped.deleteLater()


def test_network_failure_masks_declared_secret_while_local_worker_never_resolves_it(app, monkeypatch):
    secret = 'private-sync-token-for-worker-test'
    monkeypatch.setenv('SYNC_UI_TEST_SECRET', secret)
    accesses = []
    original_get = os.environ.get

    def environment_get(key, default=None):
        if key == 'SYNC_UI_TEST_SECRET':
            accesses.append(key)
        return original_get(key, default)

    def failure(*_args, **_kwargs):
        raise ac.ConfigSyncError('transport failure: ' + secret)

    monkeypatch.setattr(os.environ, 'get', environment_get)
    monkeypatch.setattr(config_sync_worker, '_sync_workspace', failure)
    network = ConfigSyncWorker(SyncUIRequest(1, 'sync', '{}', '{"secret_env":"SYNC_UI_TEST_SECRET"}'))
    local = ConfigSyncWorker(SyncUIRequest(2, 'status', '{}', '{"secret_env":"SYNC_UI_TEST_SECRET"}'))
    try:
        outcome = run(network)
        assert outcome.status == 'error' and secret not in outcome.error and '***' in outcome.error
        assert accesses == ['SYNC_UI_TEST_SECRET']
        accesses.clear()
        assert run(local).status == 'error' and accesses == []
    finally:
        network.deleteLater()
        local.deleteLater()


def test_live_store_revocation_blocks_checkpoint_and_queued_delivery(app, tmp_path, monkeypatch):
    store = UserStore(tmp_path / 'users.json')
    store.add_user(user_id='owner', display_name='Owner', role=Role.OPERATOR)
    with authorization_scope(AuthorizationContext('owner', Role.OPERATOR, store_path=str(store.path))):
        worker = ConfigSyncWorker(SyncUIRequest(1, 'status', '{}'))

    def revoked(*_args, **kwargs):
        store.set_role('owner', Role.VIEWER)
        kwargs['cancelled']()
        pytest.fail('revoked checkpoint must stop')

    monkeypatch.setattr(config_sync_worker, '_sync_workspace', revoked)
    try:
        assert run(worker).status == 'error'
        with pytest.raises(AutoControlException):
            worker.deliver(lambda: pytest.fail('revoked delivery must stop'))
    finally:
        worker.deleteLater()


@pytest.mark.parametrize('text', ['[]', '{"value":NaN}', '{' * 1500, ' ' * (1024 * 1024 + 1)],
                         ids=['array', 'nan', 'deep', 'oversized'])
def test_worker_rejects_invalid_or_unbounded_json_before_core_io(app, monkeypatch, text):
    monkeypatch.setattr(config_sync_worker, '_sync_workspace', lambda *_a, **_k: pytest.fail('invalid input'))
    worker = ConfigSyncWorker(SyncUIRequest(1, 'status', text))
    try:
        assert run(worker).status == 'error'
    finally:
        worker.deleteLater()
