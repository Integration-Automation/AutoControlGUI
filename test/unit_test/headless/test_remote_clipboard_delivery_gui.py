"""Actual queued Qt clipboard callbacks retain their concrete viewer and original local authority."""
from threading import Thread
from types import SimpleNamespace
import gc
import weakref

import pytest

pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
from headless.test_remote_registry_owners_gui import qapp as qapp, _tab
from je_auto_control.utils.clipboard import clipboard
from je_auto_control.utils.rbac import AuthorizationContext, Role, UserStore, authorization_scope, current_authorization
from je_auto_control.gui.remote_desktop import viewer_panel
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.remote_desktop.clipboard_delivery import ClipboardDelivery
from headless.test_remote_clipboard_lifecycle import controls


@pytest.fixture
def applied(monkeypatch):
    values = []
    monkeypatch.setattr(clipboard, 'set_clipboard', lambda value: values.append(('text', value)))
    monkeypatch.setattr(clipboard, 'set_clipboard_image', lambda value: values.append(('image', value)))
    return values


def enqueue(viewer, kind, value):
    worker = Thread(target=lambda: viewer.kwargs['on_clipboard'](kind, value))
    worker.start()
    worker.join(5)
    assert not worker.is_alive()


@pytest.mark.parametrize('kind,value', [('text', 'queued old text'), ('image', b'queued old image')])
@pytest.mark.parametrize('reconnect', [False, True])
def test_queued_clipboard_from_a_disconnected_gui_viewer_cannot_apply_to_a_replacement(
        qapp, applied, kind, value, reconnect):
    panel = _tab()
    old_viewer = panel._own_viewer()
    try:
        enqueue(old_viewer, kind, value)
        panel._disconnect()
        if reconnect:
            panel._connect()
        qapp.processEvents()
        assert applied == [], 'the queued clipboard from the old connection changed local state'
        if reconnect:
            enqueue(panel._own_viewer(), kind, value)
            qapp.processEvents()
            assert applied == [(kind, value)], 'the current authorised clipboard was lost'
    finally:
        panel._disconnect()
        panel.deleteLater()


@pytest.mark.parametrize('revoked', ['role', 'deleted'])
def test_queued_gui_clipboard_refreshes_its_connecting_user_before_any_native_clipboard_write(
        qapp, applied, tmp_path, revoked):
    store = UserStore(tmp_path / 'users.json')
    store.add_user(user_id='owner', display_name='Owner', role=Role.OPERATOR)
    context = AuthorizationContext('owner', Role.OPERATOR, store_path=str(store.path))
    with authorization_scope(context):
        panel = _tab()
    try:
        enqueue(panel._own_viewer(), 'text', 'revoked write')
        if revoked == 'role':
            store.set_role('owner', Role.VIEWER)
        else:
            store.remove_user('owner')
        qapp.processEvents()
        assert applied == [], 'queued clipboard work retained stale local permission'
    finally:
        panel._disconnect()
        panel.deleteLater()


def test_gui_push_refreshes_the_original_authority_before_reading_the_native_clipboard(
        qapp, applied, tmp_path, monkeypatch):
    store = UserStore(tmp_path / 'users.json')
    store.add_user(user_id='owner', display_name='Owner', role=Role.OPERATOR)
    context = AuthorizationContext('owner', Role.OPERATOR, store_path=str(store.path))
    with authorization_scope(context):
        panel = _tab()
    monkeypatch.setattr(viewer_panel.QGuiApplication, 'clipboard',
                        lambda: pytest.fail('a revoked GUI sender read the native clipboard'))
    try:
        store.set_role('owner', Role.VIEWER)
        panel._push_clipboard_to_host()
        assert applied == []
    finally:
        panel._disconnect()
        panel.deleteLater()


@pytest.mark.parametrize('kind,value', [('text', 'remote text'), ('image', b'remote image')])
def test_native_clipboard_change_notifications_do_not_echo_and_explicit_repeat_pushes_still_send(
        qapp, applied, monkeypatch, kind, value):
    from PySide6.QtCore import QObject, Signal

    class NativeClipboard(QObject):
        dataChanged = Signal()
        text_value = ''

        def text(self):
            return self.text_value

        def set(self, content):
            self.text_value = content if isinstance(content, str) else ''
            applied.append((kind, content))
            self.dataChanged.emit()

    native = NativeClipboard()
    monkeypatch.setattr(viewer_panel.QGuiApplication, 'clipboard', lambda: native)
    monkeypatch.setattr(clipboard, 'set_clipboard', native.set)
    monkeypatch.setattr(clipboard, 'set_clipboard_image', native.set)
    panel = _tab()
    peer = panel._own_viewer()
    sent = []
    monkeypatch.setattr(type(peer), 'send_clipboard_text', lambda _peer, text: sent.append(text), raising=False)
    try:
        enqueue(peer, kind, value)
        qapp.processEvents()
        assert applied == [(kind, value)] and sent == []
        native.text_value = 'deliberate repeat'
        native.dataChanged.emit()
        assert sent == []
        panel._push_clipboard_to_host()
        panel._push_clipboard_to_host()
        assert sent == ['deliberate repeat', 'deliberate repeat']
    finally:
        panel._disconnect()
        panel.deleteLater()


def test_gui_push_rechecks_authority_after_reading_before_sending(qapp, tmp_path, monkeypatch):
    store = UserStore(tmp_path / 'users.json')
    store.add_user(user_id='owner', display_name='Owner', role=Role.OPERATOR)
    context = AuthorizationContext('owner', Role.OPERATOR, store_path=str(store.path))
    with authorization_scope(context):
        panel = _tab()
    peer = panel._own_viewer()
    sent = []
    monkeypatch.setattr(type(peer), 'send_clipboard_text', lambda _peer, value: sent.append(value), raising=False)

    def revoked():
        store.set_role('owner', Role.VIEWER)
        return 'stale permission'

    monkeypatch.setattr(viewer_panel.QGuiApplication, 'clipboard', lambda: SimpleNamespace(text=revoked))
    try:
        panel._push_clipboard_to_host()
        assert sent == []
    finally:
        panel._disconnect()
        panel.deleteLater()


@pytest.mark.parametrize('original', controls(), ids=lambda value: type(value).__name__)
def test_gui_clipboard_boundary_retains_wrapped_original_controls(qapp, applied, monkeypatch, original):
    panel = _tab()

    def interrupted(_value):
        error = RuntimeError('native clipboard wrapper')
        error.__cause__ = original
        raise error

    monkeypatch.setattr(clipboard, 'set_clipboard', interrupted)
    try:
        delivery = ClipboardDelivery(panel._own_viewer(), 'text', 'controlled', DeferredAuthorization.capture())
        with pytest.raises(type(original)) as caught:
            panel._on_clipboard_main(delivery)
        assert caught.value is original and applied == []
    finally:
        panel._disconnect()
        panel.deleteLater()
        # Parametrized exception instances outlive this test; their frames must not own retired Qt wrappers.
        original.__traceback__ = None
        original.__context__ = None
        original.__cause__ = None
        caught = delivery = None


def test_gui_delivery_runs_as_its_registrant_and_restores_the_ambient_user(qapp, tmp_path, monkeypatch):
    store = UserStore(tmp_path / 'users.json')
    store.add_user(user_id='owner', display_name='Owner', role=Role.OPERATOR)
    owner = AuthorizationContext('owner', Role.OPERATOR, store_path=str(store.path))
    ambient = AuthorizationContext('ambient', Role.VIEWER)
    with authorization_scope(owner):
        panel = _tab()
    applied = []
    monkeypatch.setattr(clipboard, 'set_clipboard',
                        lambda value: applied.append((current_authorization().user_id, value)))
    try:
        enqueue(panel._own_viewer(), 'text', 'owned value')
        with authorization_scope(ambient):
            qapp.processEvents()
            assert current_authorization() is ambient
        assert applied == [('owner', 'owned value')]
    finally:
        panel._disconnect()
        panel.deleteLater()


def test_gui_delivery_rechecks_ownership_after_refreshing_the_user_store(qapp, applied, tmp_path, monkeypatch):
    store = UserStore(tmp_path / 'users.json')
    store.add_user(user_id='owner', display_name='Owner', role=Role.OPERATOR)
    context = AuthorizationContext('owner', Role.OPERATOR, store_path=str(store.path))
    with authorization_scope(context):
        panel = _tab()
    peer = panel._own_viewer()
    get = UserStore.get

    def disconnected(store, user_id):
        record = get(store, user_id)
        peer.disconnect()
        return record

    try:
        enqueue(peer, 'text', 'not written')
        monkeypatch.setattr(UserStore, 'get', disconnected)
        qapp.processEvents()
        assert applied == []
    finally:
        panel._disconnect()
        panel.deleteLater()


def test_control_exception_fixtures_do_not_retain_deleted_qt_panels(qapp, applied, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QEvent
    from je_auto_control.utils.exception.control_signals import OperationCancelledError

    created = []
    initialise = viewer_panel._ViewerPanel.__init__

    def registered(panel, *args, **kwargs):
        initialise(panel, *args, **kwargs)
        created.append(weakref.ref(panel))

    monkeypatch.setattr(viewer_panel._ViewerPanel, '__init__', registered)
    original = OperationCancelledError('fixture lifetime')
    test_gui_clipboard_boundary_retains_wrapped_original_controls(qapp, applied, monkeypatch, original)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    gc.collect()
    assert created and created[0]() is None, 'the parametrized exception retained a deleted native Qt panel'


def test_disconnected_clipboard_callback_does_not_retain_its_own_viewer_until_gc(qapp):
    panel = _tab()
    enabled = gc.isenabled()
    gc.disable()
    try:
        peer = panel._own_viewer()
        reference = weakref.ref(peer)
        panel._disconnect()
        del peer
        assert reference() is None, 'the clipboard callback retained its own viewer and native panel until arbitrary GC'
    finally:
        panel._disconnect()
        panel.deleteLater()
        if enabled:
            gc.enable()
