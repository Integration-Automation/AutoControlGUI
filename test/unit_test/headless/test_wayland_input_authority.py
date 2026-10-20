"""Real native state-machine refusals must not silently switch to an independently privileged CLI."""
from unittest.mock import MagicMock
import asyncio
from concurrent.futures import CancelledError

import pytest

from headless.test_wayland_libei import FakeLibei, KEYBOARD_DEVICE, POINTER_DEVICE, _connected
from headless.test_wayland_oeffis import FakeOeffis, HANDLE
from je_auto_control.linux_wayland import libei, oeffis, keyboard, mouse
from je_auto_control.linux_wayland import _select_input
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.exception.control_signals import OperationCancelledError


@pytest.fixture(autouse=True)
def controlled(monkeypatch):
    libei.reset_default_backend()
    monkeypatch.setattr(libei.select, 'select', lambda readable, *_args: (list(readable), [], []))
    monkeypatch.setattr(oeffis, 'is_available', lambda: True)
    monkeypatch.setenv('JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND', 'auto')
    yield
    libei.reset_default_backend()


def capture_cli(monkeypatch):
    commands = []
    monkeypatch.setattr(keyboard, '_run', lambda argv: commands.append(argv))
    monkeypatch.setattr(mouse, '_run', lambda argv: commands.append(argv))
    monkeypatch.setattr(keyboard, '_require_ydotool', lambda: '/controlled/ydotool')
    monkeypatch.setattr(mouse, '_require_ydotool', lambda: '/controlled/ydotool')
    monkeypatch.setattr(mouse, '_ydotool_point', lambda x, y: (x, y))
    monkeypatch.setattr(mouse, '_apply_accel_policy', lambda: None)
    return commands


@pytest.mark.parametrize('event', [oeffis.OEFFIS_EVENT_CLOSED, oeffis.OEFFIS_EVENT_DISCONNECTED])
@pytest.mark.parametrize('forced', ['auto', 'libei'])
@pytest.mark.parametrize('operation', ['key', 'pointer'])
def test_cancelled_portal_stops_every_layer_and_remains_blocked_without_another_dialog(
        monkeypatch, event, forced, operation):
    native = FakeLibei()
    portal = FakeOeffis(events=[event], error=b'operator refused the request')
    backend = libei.LibeiBackend(symbols=native,
                                portal_connect=lambda: oeffis.connect_eis_fd(symbols=portal))
    monkeypatch.setattr(libei, 'LibeiBackend', lambda: backend)
    monkeypatch.setenv('JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND', forced)
    commands = capture_cli(monkeypatch)
    execute = (lambda: keyboard.press_key(28)) if operation == 'key' else (lambda: mouse.set_position(20, 30))
    for _ in range(2):
        with pytest.raises(AutoControlException):
            execute()
    assert commands == [], 'portal refusal silently escalated to CLI input'
    assert sum(call[0] == 'create_session' for call in portal.calls) == 1
    assert ('unref', HANDLE) in portal.calls


@pytest.mark.parametrize('event', [libei.EI_EVENT_DEVICE_PAUSED, libei.EI_EVENT_DEVICE_REMOVED,
                                 libei.EI_EVENT_DISCONNECT])
@pytest.mark.parametrize('operation', ['key', 'pointer', 'chord'])
def test_revoked_or_paused_native_devices_cannot_send_via_the_cli(monkeypatch, event, operation):
    backend, native = _connected(session=MagicMock())
    monkeypatch.setattr(libei, '_DEFAULT_BACKEND', backend)
    device = POINTER_DEVICE if operation == 'pointer' else KEYBOARD_DEVICE
    native.pending = [(event, device)]
    commands = capture_cli(monkeypatch)
    execute = {'key': lambda: keyboard.press_key(28), 'pointer': lambda: mouse.set_position(20, 30),
               'chord': lambda: keyboard.hotkey([29, 42])}[operation]
    with pytest.raises(AutoControlException):
        execute()
    assert commands == [], 'lost native permission silently reached another input origin'


def test_compositor_disconnect_cannot_emit_on_a_later_call_after_the_event_is_consumed():
    backend, native = _connected()
    try:
        native.pending = [(libei.EI_EVENT_DISCONNECT, KEYBOARD_DEVICE)]
        for _ in range(2):
            with pytest.raises(libei.LibeiUnavailable):
                backend.press_key(28)
        assert not any(call[0] == 'key' for call in native.calls)
    finally:
        backend.disconnect()


@pytest.mark.parametrize('unavailable', ['library', 'connection'])
@pytest.mark.parametrize('operation', ['key', 'pointer', 'chord'])
def test_explicit_native_selection_never_silently_uses_cli(monkeypatch, unavailable, operation):
    commands = capture_cli(monkeypatch)
    monkeypatch.setenv('JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND', 'libei')
    if unavailable == 'library':
        monkeypatch.setattr(_select_input, '_libei_loadable', lambda: False)
    else:
        monkeypatch.setattr(_select_input, '_libei_loadable', lambda: True)
        monkeypatch.setattr(libei, 'connected_backend', lambda: None)
    execute = {'key': lambda: keyboard.press_key(28), 'pointer': lambda: mouse.set_position(20, 30),
               'chord': lambda: keyboard.hotkey([29, 42])}[operation]
    with pytest.raises(AutoControlException):
        execute()
    assert commands == [], 'a forced native backend silently selected the CLI'


@pytest.mark.parametrize('original', [KeyboardInterrupt(), SystemExit(3), GeneratorExit(), asyncio.CancelledError(),
                                      CancelledError(), OperationCancelledError('chord')],
                         ids=lambda value: type(value).__name__)
@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_interrupted_chords_release_owned_keys_and_keep_the_primary_signal(monkeypatch, original, cleanup_fails):
    backend = MagicMock()
    backend.press_key.side_effect = [None, None, original]
    if cleanup_fails:
        backend.release_key.side_effect = [OSError('controlled cleanup failure'), None]
    monkeypatch.setattr(keyboard, '_try_libei', lambda: backend)
    commands = capture_cli(monkeypatch)
    with pytest.raises(type(original)) as caught:
        keyboard.hotkey([29, 42, 46])
    assert caught.value is original
    assert [call.args for call in backend.release_key.call_args_list] == [(42,), (29,)]
    assert commands == []


def test_an_explicit_cli_choice_can_follow_a_portal_refusal_without_reopening_it(monkeypatch):
    portal = FakeOeffis(events=[oeffis.OEFFIS_EVENT_CLOSED])
    backend = libei.LibeiBackend(symbols=FakeLibei(),
                                portal_connect=lambda: oeffis.connect_eis_fd(symbols=portal))
    monkeypatch.setattr(libei, 'LibeiBackend', lambda: backend)
    commands = capture_cli(monkeypatch)
    with pytest.raises(libei.LibeiUnavailable) as caught:
        keyboard.press_key(28)
    assert caught.value.state == 'needs_permission' and not caught.value.status.fallback_allowed
    monkeypatch.setenv('JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND', 'cli')
    keyboard.press_key(28)
    assert commands == [['/controlled/ydotool', 'key', '28:1']]
    assert sum(call[0] == 'create_session' for call in portal.calls) == 1


def test_explicit_reset_allows_a_fresh_portal_grant_and_native_input(monkeypatch):
    portal = FakeOeffis(events=[oeffis.OEFFIS_EVENT_CLOSED])
    backend = libei.LibeiBackend(symbols=FakeLibei(),
                                portal_connect=lambda: oeffis.connect_eis_fd(symbols=portal))
    monkeypatch.setattr(libei, 'LibeiBackend', lambda: backend)
    commands = capture_cli(monkeypatch)
    with pytest.raises(libei.LibeiUnavailable):
        keyboard.press_key(28)
    portal._events = [oeffis.OEFFIS_EVENT_CONNECTED_TO_EIS]
    libei.reset_default_backend()
    keyboard.press_key(28)
    assert commands == []
    assert sum(call[0] == 'create_session' for call in portal.calls) == 2
    assert any(call[0] == 'key' for call in backend._symbols.calls)


@pytest.mark.parametrize('kind', ['pause', 'remove'])
def test_native_device_resume_or_replacement_can_restore_the_same_live_session(monkeypatch, kind):
    backend, native = _connected()
    monkeypatch.setattr(libei, '_DEFAULT_BACKEND', backend)
    commands = capture_cli(monkeypatch)
    event = libei.EI_EVENT_DEVICE_PAUSED if kind == 'pause' else libei.EI_EVENT_DEVICE_REMOVED
    native.pending = [(event, KEYBOARD_DEVICE)]
    with pytest.raises(libei.LibeiUnavailable):
        keyboard.press_key(28)
    native.pending = ([(libei.EI_EVENT_DEVICE_ADDED, KEYBOARD_DEVICE)] if kind == 'remove' else [])
    native.pending.append((libei.EI_EVENT_DEVICE_RESUMED, KEYBOARD_DEVICE))
    keyboard.press_key(28)
    assert commands == []
    assert len([call for call in native.calls if call[0] == 'key']) == 1


@pytest.mark.parametrize('boundary', ['keyboard', 'mouse', 'availability', 'emission'])
def test_wrapped_cancellation_never_becomes_an_optional_backend_miss(monkeypatch, boundary):
    original = OperationCancelledError('native input')

    def interrupted(*_args, **_kwargs):
        error = RuntimeError('native wrapper')
        error.__cause__ = original
        raise error

    commands = capture_cli(monkeypatch)
    if boundary in ('keyboard', 'mouse'):
        monkeypatch.setattr(_select_input, 'active_backend', interrupted)
    elif boundary == 'availability':
        monkeypatch.setattr(libei, 'get_default_backend', interrupted)
    calls = {'keyboard': lambda: keyboard.press_key(28), 'mouse': lambda: mouse.set_position(20, 30),
             'availability': lambda: _select_input.select_input_backend({}),
             'emission': lambda: _select_input.emitted(object(), interrupted)}
    with pytest.raises(OperationCancelledError) as caught:
        calls[boundary]()
    assert caught.value is original and commands == []


def test_portal_timeout_remains_a_permission_refusal_not_a_cli_request(monkeypatch):
    portal = FakeOeffis()
    backend = libei.LibeiBackend(symbols=FakeLibei(),
                                portal_connect=lambda: oeffis.connect_eis_fd(symbols=portal, timeout=0))
    monkeypatch.setattr(libei, 'LibeiBackend', lambda: backend)
    commands = capture_cli(monkeypatch)
    with pytest.raises(libei.LibeiUnavailable) as caught:
        keyboard.press_key(28)
    assert caught.value.state == 'needs_permission' and commands == []
    assert ('unref', HANDLE) in portal.calls


def test_incomplete_native_handshake_stops_and_closes_its_portal_session(monkeypatch):
    session = MagicMock()
    backend = libei.LibeiBackend(symbols=FakeLibei(events=[]), portal_connect=lambda: (7, session))
    connect = backend.connect
    monkeypatch.setattr(backend, 'connect', lambda: connect(timeout=0))
    monkeypatch.setattr(libei, 'LibeiBackend', lambda: backend)
    commands = capture_cli(monkeypatch)
    for _ in range(2):
        with pytest.raises(libei.LibeiUnavailable) as caught:
            keyboard.press_key(28)
        assert caught.value.state == 'failed' and not caught.value.status.fallback_allowed
    assert commands == []
    session.close.assert_called_once()


@pytest.mark.parametrize('phase', ['setup', 'dispatch'])
@pytest.mark.parametrize('failure', ['result', 'exception'])
def test_native_failure_after_a_portal_grant_cannot_select_cli(monkeypatch, phase, failure):
    native = FakeLibei()
    session = MagicMock()
    backend = libei.LibeiBackend(symbols=native, portal_connect=lambda: (7, session))
    if phase == 'setup':
        native.ei_setup_backend_fd = MagicMock(return_value=-1)
        if failure == 'exception':
            native.ei_setup_backend_fd.side_effect = OSError('controlled fd setup failure')
    else:
        native.ei_dispatch = MagicMock(side_effect=(OSError('controlled dispatch failure') if failure == 'exception'
                                                   else libei.LibeiUnavailable('controlled protocol failure')))
    monkeypatch.setattr(libei, 'LibeiBackend', lambda: backend)
    commands = capture_cli(monkeypatch)
    for _ in range(2):
        with pytest.raises(libei.LibeiUnavailable) as caught:
            keyboard.press_key(28)
        assert caught.value.state == 'failed' and not caught.value.status.fallback_allowed
    assert commands == []
    session.close.assert_called_once()
