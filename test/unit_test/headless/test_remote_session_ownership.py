"""Owned remote connections never replace or disconnect unrelated resources."""
import importlib

import pytest

registry_module = importlib.import_module('je_auto_control.utils.remote_desktop.registry')


class Viewer:
    """A transport double with no network, screen, clipboard or input side effects."""

    def __init__(self, **options):
        self.options = options
        self.connected = True
        self.remote_host_id = '123456789'
        self.inputs = []
        self.closed = 0

    def connect(self, timeout=5.0):
        self.connected = True

    def disconnect(self, timeout=2.0):
        self.connected = False
        self.closed += 1

    def send_input(self, action):
        self.inputs.append(action)

    def set_file_receiver(self, receiver):
        self.receiver = receiver

    def stop(self):
        self.disconnect()


class Host(Viewer):
    def __init__(self, **options):
        super().__init__(**options)
        self.is_running = False
        self.port = 1
        self.host_id = '123456789'
        self.connected_clients = 0

    def start(self):
        self.is_running = True

    def stop(self, timeout=2.0):
        self.is_running = False
        self.disconnect(timeout)

    def latest_frame(self):
        return None


class WebRTCViewer(Viewer):
    def set_file_received_callback(self, callback):
        self.file_callback = callback

    def set_inbox_listing_callback(self, callback):
        self.listing_callback = callback

    def set_inbox_op_result_callback(self, callback):
        self.operation_callback = callback


@pytest.fixture
def directory():
    return registry_module._RemoteDesktopRegistry()


def owned(directory, owner, *, transport='tcp', default=False):
    resource = Viewer()
    session = directory.register_session(
        resource, owner=owner, transport=transport, role='viewer',
        script_default=default,
    )
    return session, resource


def test_panel_disconnect_only_own_session(directory):
    left, first = owned(directory, 'panel:left')
    right, second = owned(directory, 'panel:right')
    result = directory.disconnect_session(left.id, owner=left.owner)
    assert result.state == 'closed'
    assert first.closed == 1
    assert directory.get_session(right.id).connected is True
    assert second.closed == 0
    directory.disconnect_session(right.id, owner=right.owner)


def test_stale_callback_is_ignored(directory):
    old, _ = owned(directory, 'panel:left')
    delivered = []
    callback = directory.bind_callback(old.id, delivered.append)
    callback(b'first')
    directory.disconnect_session(old.id, owner=old.owner)
    current, _ = owned(directory, 'panel:left')
    callback(b'stale')
    directory.bind_callback(current.id, delivered.append)(b'current')
    assert delivered == [b'first', b'current']


def test_default_script_session_is_compatible(directory, monkeypatch):
    monkeypatch.setattr(registry_module, 'RemoteDesktopViewer', Viewer)
    status = directory.connect_viewer('127.0.0.1', 1, 'test-only')
    script = directory.get_session(status['session_id'])
    gui, gui_resource = owned(directory, 'panel:left')
    assert directory.script_session_id('tcp', 'viewer') == script.id
    directory.send_input({'action': 'ping'})
    assert directory.viewer.inputs == [{'action': 'ping'}]
    directory.send_input({'action': 'named'}, session_id=gui.id)
    assert gui_resource.inputs == [{'action': 'named'}]
    directory.disconnect_viewer()
    assert directory.get_session(gui.id).connected is True
    assert gui_resource.closed == 0


def test_wrong_owner_cannot_disconnect(directory):
    session, resource = owned(directory, 'panel:left')
    with pytest.raises(PermissionError):
        directory.disconnect_session(session.id, owner='panel:right')
    assert resource.connected and resource.closed == 0


@pytest.mark.parametrize('transport', ['tcp', 'ws', 'webrtc'])
def test_script_aliases_are_transport_specific(directory, transport):
    script, resource = owned(directory, 'script', transport=transport, default=True)
    other, _ = owned(directory, 'panel:left', transport=transport)
    assert directory.script_session_id(transport, 'viewer') == script.id
    directory.disconnect_session(script.id)
    assert resource.closed == 1
    assert directory.get_session(other.id).connected


def test_lifecycle_events_identify_only_the_owner(directory):
    left, _ = owned(directory, 'panel:left')
    right, _ = owned(directory, 'panel:right')
    directory.disconnect_session(left.id, owner=left.owner)
    events = directory.session_events(owner=left.owner)
    assert [event.state for event in events] == ['active', 'closing', 'closed']
    assert all(event.session_id == left.id and event.owner == left.owner for event in events)
    assert [event.state for event in directory.session_events(owner=right.owner)] == ['active']


def test_closed_session_id_cannot_be_reused(directory):
    first, _ = owned(directory, 'panel:left')
    directory.disconnect_session(first.id)
    with pytest.raises(ValueError):
        directory.register_session(
            Viewer(), owner=first.owner, transport='tcp', role='viewer', session_id=first.id,
        )


def test_wrong_transport_does_not_send_input(directory):
    session, resource = owned(directory, 'panel:left', transport='ws')
    with pytest.raises(ValueError):
        directory.send_input({'action': 'ping'}, session_id=session.id)
    assert resource.inputs == []


def test_lifecycle_notifications_are_owner_scoped(directory):
    left, _ = owned(directory, 'panel:left')
    right, _ = owned(directory, 'panel:right')
    delivered = []
    remove = directory.subscribe_sessions(left.owner, delivered.append)
    directory.disconnect_session(right.id)
    assert delivered == []
    directory.disconnect_session(left.id)
    assert [event.state for event in delivered] == ['closing', 'closed']
    remove()


_APPLICATION = None


@pytest.fixture
def panels(directory, monkeypatch, tmp_path):
    global _APPLICATION
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.remote_desktop import viewer_panel
    _APPLICATION = QApplication.instance() or QApplication([])
    monkeypatch.setattr(viewer_panel, 'registry', directory)
    monkeypatch.setattr(viewer_panel, 'RemoteDesktopViewer', Viewer)
    monkeypatch.setattr(viewer_panel, 'default_download_dir', lambda: tmp_path)
    widgets = [viewer_panel._ViewerPanel(), viewer_panel._ViewerPanel()]
    for widget in widgets:
        widget._host_field.setText('127.0.0.1')
        widget._port.setValue(1)
        widget._token.setText('test-only')
    yield widgets
    for widget in widgets:
        widget._disconnect()
        widget.close()
        widget.deleteLater()
    _APPLICATION.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    _APPLICATION.processEvents()


def test_actual_panels_keep_connections_independent(directory, panels):
    left, right = panels
    left._connect()
    first = directory.session_resource(left._session_id, owner=left._session_owner)
    right._connect()
    second = directory.session_resource(right._session_id, owner=right._session_owner)
    left._disconnect()
    assert first.closed == 1
    assert second.connected and second.closed == 0
    right._send({'action': 'ping'})
    assert second.inputs == [{'action': 'ping'}]


def test_queued_old_gui_frame_does_not_reach_replacement(directory, panels):
    import threading
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice
    from PySide6.QtGui import QImage
    panel = panels[0]
    panel._connect()
    first = directory.session_resource(panel._session_id, owner=panel._session_owner)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    QImage(2, 2, QImage.Format.Format_RGB32).save(buffer, 'JPEG')
    callback = first.options['on_frame']
    thread = threading.Thread(target=lambda: callback(bytes(data)))
    thread.start()
    thread.join(2)
    panel._disconnect()
    panel._connect()
    _APPLICATION.processEvents()
    assert panel._screen_window.display.has_image() is False


@pytest.mark.parametrize('kind', ['host', 'quick'])
def test_hosting_panel_keeps_script_viewer_alive(directory, panels, monkeypatch, kind):
    from PySide6.QtCore import QEvent
    from je_auto_control.gui.remote_desktop import host_panel, connection_screen
    module = host_panel if kind == 'host' else connection_screen
    monkeypatch.setattr(module, 'registry', directory)
    monkeypatch.setattr(module, 'RemoteDesktopHost', Host)
    _, script_resource = owned(directory, 'script', default=True)
    widget = module._HostPanel() if kind == 'host' else module.QuickConnectScreen()
    try:
        if kind == 'host':
            widget._token.setText('test-only')
            widget._start()
        else:
            widget._host_token.setText('test-only')
            widget._start_hosting()
        assert script_resource.connected and script_resource.closed == 0
    finally:
        if kind == 'host':
            widget._stop()
        else:
            widget._stop_hosting()
        widget.close()
        widget.deleteLater()
        _APPLICATION.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


@pytest.fixture
def webrtc_panels(directory, panels, monkeypatch):
    from PySide6.QtCore import QEvent
    from je_auto_control.gui.remote_desktop import webrtc_panel
    module = importlib.import_module(webrtc_panel._WebRTCViewerPanel.__module__)
    monkeypatch.setattr(module, 'WebRTCDesktopViewer', WebRTCViewer)
    monkeypatch.setattr(module, 'load_or_create_viewer_id', lambda: 'test-only-viewer')
    monkeypatch.setattr(module, 'registry', directory)
    widgets = [webrtc_panel._WebRTCViewerPanel(), webrtc_panel._WebRTCViewerPanel()]
    yield widgets
    for widget in widgets:
        widget._stop_viewer_if_any()
        widget.close()
        widget.deleteLater()
    _APPLICATION.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def test_webrtc_panels_own_only_their_connections(directory, webrtc_panels):
    left, right = webrtc_panels
    left._viewer = left._build_viewer('test-only')
    right._viewer = right._build_viewer('test-only')
    second = right._viewer
    assert directory.session_resource(left._sessions.id('viewer'), owner=left._sessions.owner) is left._viewer
    left._stop_viewer_if_any()
    assert second.connected and second.closed == 0


def test_webrtc_queued_state_is_generation_checked(directory, webrtc_panels):
    import threading
    panel = webrtc_panels[0]
    panel._viewer = panel._build_viewer('test-only')
    callback = panel._viewer.options['on_state_change']
    thread = threading.Thread(target=lambda: callback('old-state'))
    thread.start()
    thread.join(2)
    panel._stop_viewer_if_any()
    panel._viewer = panel._build_viewer('test-only')
    panel._status_label.setText('CURRENT')
    _APPLICATION.processEvents()
    assert panel._status_label.text() == 'CURRENT'


def test_webrtc_panel_uses_the_standard_file_budget():
    from pathlib import Path
    path = Path(__file__).resolve().parents[3] / 'je_auto_control/gui/remote_desktop/webrtc_panel.py'
    assert len(path.read_text(encoding='utf-8').splitlines()) <= 750


def test_panel_retains_failed_cleanup_for_retry(directory, panels):
    controller = panels[0]._sessions
    session = controller.reserve('tcp', 'viewer')
    resource = Viewer()
    original = resource.disconnect
    calls = []

    def disconnect(timeout=2.0):
        calls.append(timeout)
        if len(calls) == 1:
            raise OSError('cleanup still draining')
        original(timeout)

    resource.disconnect = disconnect
    controller.attach(resource, 'viewer')
    with pytest.raises(OSError):
        controller.close('viewer')
    assert controller.id('viewer') == session.id
    assert directory.get_session(session.id).state == 'failed'
    controller.close('viewer')
    assert resource.closed == 1 and controller.id('viewer') is None


def test_remote_approval_cannot_target_replacement_host(panels, monkeypatch):
    import types
    from PySide6.QtCore import QEvent
    from je_auto_control.gui.remote_desktop import webrtc_panel
    panel = webrtc_panel._WebRTCHostPanel()
    calls = []
    old = types.SimpleNamespace(session_count=lambda: 1)
    replacement = types.SimpleNamespace(approve_pending_viewer=calls.append, session_count=lambda: 1,
                                        list_sessions=lambda: [], screen_track=lambda: None,
                                        first_session_pc=lambda: None)
    panel._multi_host = old

    class Dialog:
        AcceptAndTrust, AcceptOnce = 2, 1

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            panel._multi_host = replacement

        def choice(self):
            return self.AcceptOnce

    monkeypatch.setattr(importlib.import_module(panel.__class__.__module__), 'PendingViewerDialog', Dialog)
    try:
        panel._on_pending_viewer('old-peer', 'viewer')
        assert calls == []
    finally:
        panel._multi_host = None
        panel.close()
        panel.deleteLater()
        _APPLICATION.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def test_panel_disposal_cleans_other_roles_after_one_failure(directory, panels):
    controller = panels[0]._sessions
    first = controller.reserve('tcp', 'host')
    failing = Host()

    def fail(timeout=2.0):
        raise OSError('still draining')

    failing.stop = fail
    controller.attach(failing, 'host')
    second = controller.reserve('tcp', 'viewer')
    viewer = Viewer()
    controller.attach(viewer, 'viewer')
    controller.dispose()
    assert directory.get_session(first.id).state == 'failed'
    assert directory.get_session(second.id).state == 'closed' and viewer.closed == 1
    failing.stop = lambda timeout=2.0: None
    directory.disconnect_session(first.id)


def test_webrtc_disposal_stops_owned_background_resources(webrtc_panels):
    import types
    panel = webrtc_panels[0]
    stopped = []
    panel._stats_poller = types.SimpleNamespace(stop=lambda: stopped.append('stats'))
    panel._recorder = types.SimpleNamespace(stop=lambda: stopped.append('recorder'))
    panel._sync_engine = types.SimpleNamespace(stop=lambda: stopped.append('sync'))
    panel._sessions.dispose()
    assert stopped == ['stats', 'recorder', 'sync']
    panel._stats_poller = panel._recorder = panel._sync_engine = None


@pytest.mark.parametrize('transport,method', [('tcp', 'send_input'), ('ws', 'ws_send_input'),
                                            ('webrtc', 'webrtc_send_input')])
def test_registry_operation_captures_one_resource(directory, monkeypatch, transport, method):
    first, replacement = Viewer(), Viewer()
    calls = []

    def changing_resource(*args):
        calls.append(args)
        return first if len(calls) == 1 else replacement

    monkeypatch.setattr(directory, '_resource', changing_resource)
    getattr(directory, method)({'action': 'ping'})
    assert first.inputs == [{'action': 'ping'}] and replacement.inputs == []
    assert len(calls) == 1


def test_named_webrtc_answer_returns_named_status(directory):
    import types
    answers = []
    host = types.SimpleNamespace(authenticated=True, connection_state='connected', accept_answer=answers.append,
                                 stop=lambda: None)
    session = directory.register_session(host, owner='gui:test', transport='webrtc', role='host')
    status = directory.webrtc_accept_answer('answer', session_id=session.id)
    assert status['session_id'] == session.id and status['authenticated'] is True
    assert answers == ['answer']


def test_named_multi_viewer_status_supports_gui_host(directory):
    import types
    host = types.SimpleNamespace(list_sessions=lambda: [{'authenticated': True, 'state': 'connected'}],
                                 stop_all=lambda: None)
    session = directory.register_session(host, owner='gui:test', transport='webrtc', role='host')
    status = directory.webrtc_host_status(session_id=session.id)
    assert status['session_id'] == session.id and status['authenticated'] is True
    assert status['connected_clients'] == 1


def test_quick_approval_rechecks_generation_after_modal(directory, panels, monkeypatch):
    import types
    from PySide6.QtCore import QEvent
    from je_auto_control.gui.remote_desktop import connection_screen as module
    monkeypatch.setattr(module, 'registry', directory)
    panel = module.QuickConnectScreen()
    session = panel._sessions.reserve('tcp', 'host')
    panel._sessions.attach(Host(), 'host')
    pending = types.SimpleNamespace(address=('127.0.0.1', 1), transport='tcp')
    request = module._ApprovalRequest(pending, session)
    original_box = module.QMessageBox

    class Dialog:
        Icon, ButtonRole = original_box.Icon, original_box.ButtonRole

        def __init__(self, parent):
            self.buttons = []

        def __getattr__(self, name):
            return lambda *args: None

        def addButton(self, *args):
            button = object()
            self.buttons.append(button)
            return button

        def exec(self):
            panel._sessions.close('host')

        def clickedButton(self):
            return self.buttons[0]

    monkeypatch.setattr(module, 'QMessageBox', Dialog)
    monkeypatch.setattr(module, 'QTimer', types.SimpleNamespace(singleShot=lambda *args: None))
    try:
        panel._show_approval_dialog(request)
        assert request.decision == 'denied' and request.event.is_set()
    finally:
        panel.close()
        panel.deleteLater()
        _APPLICATION.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
