"""A refused native coordinate cannot change input origin or allow a subsequent click to escape its region."""
import asyncio
from concurrent.futures import CancelledError
from types import SimpleNamespace

import pytest

from headless.test_wayland_libei import FakeLibei, POINTER_DEVICE, _connected
from je_auto_control.linux_wayland import libei, mouse, _select_input
from je_auto_control.utils.exception.control_signals import OperationCancelledError

_EMISSIONS = frozenset({'motion', 'frame', 'key', 'button', 'scroll'})


@pytest.fixture
def sender(monkeypatch):
    env = {'JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND': 'auto'}
    monkeypatch.setattr(_select_input, 'os', SimpleNamespace(environ=env))
    monkeypatch.setattr(libei, 'select', SimpleNamespace(select=lambda items, *_args: (list(items), [], [])))
    native = FakeLibei(regions={POINTER_DEVICE: [(0, 0, 100, 100)]})
    backend, _ = _connected(native)
    native.calls.clear()
    monkeypatch.setattr(libei, '_DEFAULT_BACKEND', backend)
    monkeypatch.setattr(libei, '_BLOCKED_PROBE', None)
    monkeypatch.setattr(libei, '_PROBE_FAILED', False)
    monkeypatch.setattr(libei, 'layout_origin', lambda: (0, 0))
    monkeypatch.setattr(mouse, 'layout_origin', lambda: (0, 0))
    commands = []
    monkeypatch.setattr(mouse, '_run', lambda argv: commands.append(argv))
    monkeypatch.setattr(mouse, '_require_ydotool', lambda: '/controlled/ydotool')
    monkeypatch.setattr(mouse, '_apply_accel_policy', lambda: None)
    try:
        yield backend, native, env, commands
    finally:
        backend.disconnect()


@pytest.mark.parametrize('mode', ['auto', 'libei'])
@pytest.mark.parametrize('operation', ['move', 'click'])
@pytest.mark.parametrize('regions,origin,point', [
    ([(0, 0, 100, 100)], (0, 0), (100, 40)),
    ([(0, 0, 100, 100)], (0, 0), (40, 100)),
    ([(0, 0, 100, 100)], (0, 0), (-1, 40)),
    ([(0, 0, 100, 100), (200, 0, 100, 100)], (0, 0), (150, 40)),
    ([(0, 0, 100, 100)], (-100, -50), (-101, -50)),
    ([(0, 0, 100, 100)], (-100, -50), (500, 500)),
])
def test_out_of_region_native_refusal_stops_before_cli_motion_frame_or_click(
        sender, monkeypatch, mode, operation, regions, origin, point):
    _backend, native, env, commands = sender
    env['JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND'] = mode
    native.regions[POINTER_DEVICE] = regions
    monkeypatch.setattr(libei, 'layout_origin', lambda: origin)
    action = (lambda: mouse.set_position(*point)) if operation == 'move' else (
        lambda: mouse.click_mouse(mouse.wayland_mouse_left, *point))
    with pytest.raises(libei.LibeiUnavailable, match='outside every region') as caught:
        action()
    assert caught.value.state == 'failed' and caught.value.status.fallback_allowed is False
    assert commands == [] and not [call for call in native.calls if call[0] in _EMISSIONS]


@pytest.mark.parametrize('regions,origin,point,expected', [
    ([(0, 0, 100, 100)], (0, 0), (20, 30), (20.0, 30.0)),
    ([(0, 0, 100, 100)], (-100, -50), (-100, -50), (0.0, 0.0)),
    ([(0, 0, 100, 100)], (-100, -50), (20, 30), (20.0, 30.0)),
    ([(0, 0, 100, 100), (100, 0, 100, 100)], (0, 0), (100, 50), (100.0, 50.0)),
    ([(0, 0, 100, 100)], (100, 50), (110, 60), (10.0, 10.0)),
    ([], (0, 0), (-900, 4000), (-900.0, 4000.0)),
])
def test_valid_native_mapping_raw_priority_and_unbounded_devices_are_preserved(
        sender, monkeypatch, regions, origin, point, expected):
    _backend, native, _env, commands = sender
    native.regions[POINTER_DEVICE] = regions
    monkeypatch.setattr(libei, 'layout_origin', lambda: origin)
    mouse.set_position(*point)
    assert ('motion', POINTER_DEVICE, *expected) in native.calls
    assert len([call for call in native.calls if call[0] == 'frame']) == 1 and commands == []


@pytest.mark.parametrize('mode', ['auto', 'libei'])
def test_invalid_request_does_not_revoke_the_sender_or_prevent_a_later_valid_move(sender, mode):
    backend, native, env, commands = sender
    env['JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND'] = mode
    with pytest.raises(libei.LibeiUnavailable):
        mouse.set_position(150, 150)
    assert backend.is_connected
    mouse.set_position(20, 30)
    assert ('motion', POINTER_DEVICE, 20.0, 30.0) in native.calls and commands == []


def test_an_explicit_cli_choice_remains_an_independent_provider(sender):
    _backend, native, env, commands = sender
    env['JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND'] = 'cli'
    mouse.set_position(150, 150)
    assert commands == [['/controlled/ydotool', 'mousemove', '--absolute', '-x', '150', '-y', '150']]
    assert not [call for call in native.calls if call[0] in _EMISSIONS]


@pytest.mark.parametrize('original', [KeyboardInterrupt(), SystemExit(7), GeneratorExit(), asyncio.CancelledError(),
                                      CancelledError(), OperationCancelledError('pointer regions')],
                         ids=lambda value: type(value).__name__)
@pytest.mark.parametrize('wrapped', [False, True])
def test_region_lookup_controls_remain_original_and_never_emit_or_fallback(sender, monkeypatch, original, wrapped):
    backend, native, _env, commands = sender
    failure = libei.LibeiUnavailable('wrapped region lookup') if wrapped else original
    if wrapped:
        failure.__cause__ = original

    def interrupted(_device):
        raise failure

    monkeypatch.setattr(backend, '_device_regions', interrupted)
    with pytest.raises(type(original)) as caught:
        mouse.set_position(20, 30)
    assert caught.value is original and commands == []
    assert not [call for call in native.calls if call[0] in _EMISSIONS]
