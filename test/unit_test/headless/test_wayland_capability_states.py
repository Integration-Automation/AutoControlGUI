"""Passive capability snapshots separate prerequisites, observed authority and XWayland scope."""
import importlib
import json
import sys
from types import SimpleNamespace

import pytest

from je_auto_control.linux_wayland import libei, _select_input
from je_auto_control.linux_wayland._input_state import InputFailure
from je_auto_control.utils.exception.exceptions import AutoControlException


@pytest.fixture
def api(monkeypatch):
    module = importlib.import_module('je_auto_control.wrapper.capabilities')
    # Keep platform/environment/PATH fakes local to this module while unrelated Qt workers can still run.
    monkeypatch.setattr(module, 'sys', SimpleNamespace(platform='linux', modules=sys.modules))
    monkeypatch.setattr(module, 'os', SimpleNamespace(environ={}))
    monkeypatch.setattr(module, 'shutil', SimpleNamespace(which=lambda _name: None))
    return module


def context(api, *, env=None, tools=(), **kwargs):
    return api.BackendContext('linux', env or {'XDG_SESSION_TYPE': 'wayland'}, frozenset(tools), **kwargs)


def test_cancel_does_not_fallback_silently(api, monkeypatch):
    monkeypatch.setattr(libei, '_BLOCKED_PROBE', InputFailure('needs_permission', 'portal', 'private detail'))
    monkeypatch.setattr(libei, '_DEFAULT_BACKEND', None)
    monkeypatch.setattr(api.sys, 'platform', 'linux')
    monkeypatch.setitem(api.os.environ, 'XDG_SESSION_TYPE', 'wayland')
    monkeypatch.setattr(api.shutil, 'which', lambda _name: '/controlled/executable')
    canceled = api.probe_capabilities(api.BackendContext.current()).input
    assert canceled.state == 'needs_permission'
    assert canceled.backend == 'libei' and canceled.recovery
    assert 'private detail' not in json.dumps(canceled.to_dict())


def test_revoked_session_cannot_send(api, monkeypatch):
    writes = []
    backend = libei.LibeiBackend(symbols=SimpleNamespace(ei_device_keyboard_key=lambda *_args: writes.append(True)))
    backend._ei, backend._revoked = 1, True
    monkeypatch.setattr(libei, '_DEFAULT_BACKEND', backend)
    monkeypatch.setattr(libei, '_BLOCKED_PROBE', None)
    monkeypatch.setattr(api.sys, 'platform', 'linux')
    monkeypatch.setitem(api.os.environ, 'XDG_SESSION_TYPE', 'wayland')
    with pytest.raises(libei.LibeiUnavailable):
        _select_input.emitted(backend, lambda sender: sender.press_key(30))
    snapshot = api.probe_capabilities(api.BackendContext.current())
    assert len(writes) == 0 and snapshot.input.state == 'revoked'


def test_xwayland_scope_is_explicit(api):
    env = {'XDG_SESSION_TYPE': 'wayland', 'DISPLAY': ':9', 'JE_AUTOCONTROL_LINUX_DISPLAY_SERVER': 'x11'}
    snapshot = api.probe_capabilities(context(api, env=env))
    assert snapshot.input.desktop_wide is False and snapshot.capture.desktop_wide is False
    assert snapshot.display_server == 'x11' and snapshot.capture.backend == 'x11'


def test_xwayland_observation_cannot_broaden_its_native_window_scope(api):
    env = {'WAYLAND_DISPLAY': 'w', 'DISPLAY': ':9', 'JE_AUTOCONTROL_LINUX_DISPLAY_SERVER': 'x11'}
    previous = api.CapabilityStatus('input', 'available', 'x11', 'observed', 'verify operation', True)
    snapshot = api.probe_capabilities(context(api, env=env, input_state=previous))
    assert snapshot.input.state == 'available' and snapshot.input.desktop_wide is False


def test_an_existing_x11_scope_restriction_is_never_broadened(api):
    observed = api.CapabilityStatus('capture', 'available', 'x11', 'limited observer', 'verify scope', False)
    snapshot = api.probe_capabilities(context(api, env={'DISPLAY': ':9'}, capture_state=observed))
    assert snapshot.capture.desktop_wide is False


@pytest.mark.parametrize('state', ['needs_permission', 'paused', 'revoked', 'failed'])
def test_observed_native_refusal_outweighs_installed_cli_tools(api, state):
    observed = api.CapabilityStatus('input', state, 'libei', 'observed refusal', 'explicit recovery', True)
    snapshot = api.probe_capabilities(context(api, tools=('ydotool', 'grim'), input_state=observed))
    assert snapshot.input is observed and snapshot.capture.backend == 'grim'
    assert snapshot.capture.state == 'unverified'


def test_dependency_detection_is_not_readiness_or_permission(api):
    snapshot = api.probe_capabilities(context(api, tools=('ydotool', 'grim')))
    assert snapshot.input.state == snapshot.capture.state == 'unverified'
    assert snapshot.input.backend == 'auto' and snapshot.capture.backend == 'grim'
    assert snapshot.to_dict()['passive'] is True


def test_input_and_capture_dependencies_are_independent(api):
    env = {'XDG_SESSION_TYPE': 'wayland', 'JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND': 'cli'}
    snapshot = api.probe_capabilities(context(api, env=env, tools=('grim',)))
    assert snapshot.input.state == 'needs_dependency' and snapshot.input.backend == 'ydotool'
    assert snapshot.capture.state == 'unverified' and snapshot.capture.backend == 'grim'


def test_explicit_cli_selection_does_not_claim_a_running_daemon(api):
    env = {'WAYLAND_DISPLAY': 'wayland-0', 'JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND': 'cli'}
    snapshot = api.probe_capabilities(context(api, env=env, tools=('ydotool',)))
    assert snapshot.input.state == 'unverified' and snapshot.input.backend == 'ydotool'
    assert snapshot.capture.state == 'needs_dependency'


@pytest.mark.parametrize('template', ['bad "quote', 'capture --no-output'])
def test_invalid_explicit_capture_command_never_selects_a_different_provider(api, template):
    env = {'WAYLAND_DISPLAY': 'wayland-0', 'JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND': template}
    snapshot = api.probe_capabilities(context(api, env=env, tools=('grim', 'capture')))
    assert snapshot.capture.state == 'failed' and snapshot.capture.backend == 'custom-command'


def test_portal_bus_address_is_only_a_prerequisite_and_is_not_disclosed(api):
    secret = 'unix:path=/private/session-with-token'
    snapshot = api.probe_capabilities(context(api, env={'WAYLAND_DISPLAY': 'w', 'DBUS_SESSION_BUS_ADDRESS': secret}))
    assert snapshot.capture.backend == 'portal' and snapshot.capture.state == 'unverified'
    assert secret not in json.dumps(snapshot.to_dict())


def test_context_is_an_immutable_detached_environment_snapshot(api):
    env = {'DISPLAY': ':9'}
    captured = context(api, env=env)
    env['DISPLAY'] = ':changed'
    assert captured.environ['DISPLAY'] == ':9'
    with pytest.raises(TypeError):
        captured.environ['DISPLAY'] = ':injected'


def test_context_rejects_mismatched_observation_and_status_shape(api):
    with pytest.raises(AutoControlException):
        api.CapabilityStatus('input', 'ready-ish', 'libei', 'reason', 'recovery', True)
    capture = api.CapabilityStatus('capture', 'needs_permission', 'portal', 'reason', 'recovery', True)
    with pytest.raises(AutoControlException):
        context(api, input_state=capture)


def test_current_context_does_not_load_native_libraries_connect_or_execute_tools(api, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail('passive probing attempted a native library/session/tool operation')
    monkeypatch.setattr(libei, '_DEFAULT_BACKEND', None)
    monkeypatch.setattr(libei, '_BLOCKED_PROBE', None)
    monkeypatch.setattr(libei, '_PROBE_FAILED', False)
    monkeypatch.setattr(libei, 'bind', forbidden)
    monkeypatch.setattr(libei, 'get_default_backend', forbidden)
    monkeypatch.setattr(libei, 'connected_backend', forbidden)
    monkeypatch.setattr(api.sys, 'platform', 'linux')
    monkeypatch.setitem(api.os.environ, 'XDG_SESSION_TYPE', 'wayland')
    monkeypatch.setattr(api.shutil, 'which', lambda _name: None)
    snapshot = api.probe_capabilities(api.BackendContext.current())
    assert snapshot.input.state == 'unverified' and snapshot.capture.state in ('unverified', 'needs_dependency')


def test_existing_sender_busy_on_another_thread_is_observed_without_waiting(api, monkeypatch):
    backend = libei.LibeiBackend(symbols=SimpleNamespace())
    attempts = []
    backend._lock = SimpleNamespace(acquire=lambda *, blocking: attempts.append(blocking) or False)
    monkeypatch.setattr(libei, '_DEFAULT_BACKEND', backend)
    monkeypatch.setattr(libei, '_BLOCKED_PROBE', None)
    monkeypatch.setattr(api.sys, 'platform', 'linux')
    monkeypatch.setitem(api.os.environ, 'XDG_SESSION_TYPE', 'wayland')
    snapshot = api.probe_capabilities(api.BackendContext.current())
    assert attempts == [False] and snapshot.input.state == 'unverified'


@pytest.mark.parametrize('platform,backend', [('win32', 'win32'), ('darwin', 'quartz')])
def test_non_linux_backend_presence_does_not_claim_os_permission(api, platform, backend):
    snapshot = api.probe_capabilities(api.BackendContext(platform, {}, frozenset()))
    assert snapshot.input.backend == snapshot.capture.backend == backend
    assert snapshot.input.state == snapshot.capture.state == 'unverified'


@pytest.mark.parametrize('paused', [False, True])
def test_existing_ready_or_paused_devices_are_read_without_pumping_the_protocol(api, monkeypatch, paused):
    def forbidden(*_args):
        pytest.fail('a passive observation pumped native events')
    backend = libei.LibeiBackend(symbols=SimpleNamespace())
    backend._ei, backend._handshake_complete = 1, True
    backend._devices = {capability: 8 for capability in libei._WANTED_CAPS}
    backend._emulating = {8: not paused}
    monkeypatch.setattr(backend, '_pump', forbidden)
    monkeypatch.setattr(libei, '_DEFAULT_BACKEND', backend)
    monkeypatch.setattr(libei, '_BLOCKED_PROBE', None)
    monkeypatch.setattr(api.sys, 'platform', 'linux')
    monkeypatch.setitem(api.os.environ, 'XDG_SESSION_TYPE', 'wayland')
    snapshot = api.probe_capabilities(api.BackendContext.current())
    assert snapshot.input.state == ('paused' if paused else 'available')


@pytest.mark.parametrize('condition,expected', [('partial', 'unverified'), ('button_paused', 'paused'),
                                             ('required_removed', 'revoked')])
def test_cached_native_readiness_covers_all_requested_event_families(api, monkeypatch, condition, expected):
    backend = libei.LibeiBackend(symbols=SimpleNamespace())
    backend._ei, backend._handshake_complete = 1, True
    backend._devices = {capability: index+10 for index, capability in enumerate(libei._WANTED_CAPS)}
    backend._emulating = {device: True for device in backend._devices.values()}
    if condition == 'partial':
        del backend._devices[libei.EI_DEVICE_CAP_BUTTON]
    elif condition == 'button_paused':
        backend._emulating[backend._devices[libei.EI_DEVICE_CAP_BUTTON]] = False
    else:
        del backend._devices[libei.EI_DEVICE_CAP_POINTER_ABSOLUTE]
    monkeypatch.setattr(libei, '_DEFAULT_BACKEND', backend)
    monkeypatch.setattr(libei, '_BLOCKED_PROBE', None)
    monkeypatch.setitem(api.os.environ, 'XDG_SESSION_TYPE', 'wayland')
    snapshot = api.probe_capabilities(api.BackendContext.current())
    assert snapshot.input.state == expected and snapshot.input.backend == 'libei'


@pytest.mark.parametrize('choice,backend,state', [('auto', 'ydotool', 'unverified'),
                                                ('libei', 'libei', 'needs_dependency')])
def test_only_observed_optional_absence_allows_automatic_cli_diagnostics(api, monkeypatch, choice, backend, state):
    monkeypatch.setattr(libei, '_DEFAULT_BACKEND', None)
    monkeypatch.setattr(libei, '_BLOCKED_PROBE', None)
    monkeypatch.setattr(libei, '_PROBE_FAILED', True)
    monkeypatch.setattr(api.sys, 'platform', 'linux')
    monkeypatch.setitem(api.os.environ, 'XDG_SESSION_TYPE', 'wayland')
    monkeypatch.setitem(api.os.environ, 'JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND', choice)
    monkeypatch.setattr(api.shutil, 'which', lambda _name: '/controlled')
    snapshot = api.probe_capabilities(api.BackendContext.current())
    assert snapshot.input.backend == backend and snapshot.input.state == state


def test_owned_capture_permission_observation_remains_separate_from_input(api):
    observed = api.CapabilityStatus('capture', 'needs_permission', 'portal', 'refused', 'explicit retry', True)
    env = {'WAYLAND_DISPLAY': 'w', 'DBUS_SESSION_BUS_ADDRESS': 'controlled'}
    snapshot = api.probe_capabilities(context(api, env=env, capture_state=observed))
    assert snapshot.capture is observed and snapshot.input.state == 'unverified'


def test_default_context_repr_and_result_do_not_disclose_environment_or_capture_arguments(api, monkeypatch):
    secret = 'private-capability-command-argument'
    monkeypatch.setitem(api.os.environ, 'JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND', 'controlled {output} '+secret)
    monkeypatch.setitem(api.os.environ, 'WAYLAND_DISPLAY', 'w')
    monkeypatch.setattr(api.sys, 'platform', 'linux')
    monkeypatch.setattr(api.shutil, 'which', lambda _name: '/controlled')
    captured = api.BackendContext.current()
    result = api.probe_capabilities(captured)
    assert secret not in repr(captured) and secret not in json.dumps(result.to_dict())


@pytest.mark.parametrize('invalid', [None, {}, []])
def test_invalid_unhashable_status_values_use_the_framework_error_family(api, invalid):
    with pytest.raises(AutoControlException):
        api.CapabilityStatus('input', invalid, 'libei', 'reason', 'recovery', True)
