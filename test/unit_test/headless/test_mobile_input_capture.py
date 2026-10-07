"""Mobile text, gestures and supplied-frame locators never use desktop input."""
import importlib
from types import SimpleNamespace

from PIL import Image
import pytest


def _api():
    return importlib.import_module('je_auto_control.api.mobile')


@pytest.fixture
def mobile(monkeypatch):
    api = _api()
    calls = []
    capture_calls = []
    image = Image.new('RGB', (600, 300))

    class Handle:
        orientation = 'LANDSCAPE'
        info = {'displayRotation': 1, 'displayWidth': 300, 'displayHeight': 150}

        def send_keys(self, text):
            calls.append(('text', text))

        def screenshot(self, *args, **kwargs):
            capture_calls.append('device')
            return image.copy()

        def window_size(self):
            return (300, 150)

        def _unsafe_window_size(self):
            return self.window_size()

        def click(self, x, y):
            calls.append(('tap', x, y))

        tap = click

        def long_click(self, x, y, duration):
            calls.append(('hold', x, y, duration))

        tap_hold = long_click

        def drag(self, x1, y1, x2, y2, duration):
            calls.append(('drag', x1, y1, x2, y2, duration))

        swipe = drag

        def jsonrpc_call(self, method, params=None, timeout=10):
            calls.append(('rpc', method, params, timeout))
            return True

        def _fetch(self, method, path, data=None, with_session=False, timeout=None):
            calls.append(('http', method, path, data, with_session, timeout))
            return SimpleNamespace(value=None)

    handle = Handle()
    adapter = SimpleNamespace(handle=handle, close=lambda: None)
    monkeypatch.setattr(api.DeviceSession, 'adapter', lambda self, kind: adapter)
    return SimpleNamespace(api=api, calls=calls, image=image, handle=handle, capture_calls=capture_calls)


def _session(mobile, platform='android'):
    return mobile.api.open_device(mobile.api.DeviceContext(
        platform, 'phone-a', target='http://127.0.0.1:8100' if platform == 'ios' else 'phone-a'))


@pytest.mark.parametrize('platform', ['android', 'ios'])
def test_unicode_round_trip(mobile, platform):
    with _session(mobile, platform) as session:
        session.type_text('測試 café 🙂')
    received_text = mobile.calls[0][1]
    assert received_text == '測試 café 🙂'


@pytest.mark.parametrize('platform', ['android', 'ios'])
def test_long_press_drag_pinch(mobile, platform):
    api = mobile.api
    with _session(mobile, platform) as session:
        session.perform(api.Gesture('long_press', ((40, 60),), duration_s=1))
        session.perform(api.Gesture('drag', ((40, 60), (70, 90))))
        session.perform(api.Gesture('pinch', ((40, 60), (70, 90), (20, 40), (90, 110))))
    assert mobile.calls[0] == ('hold', 40, 60, 1)
    assert mobile.calls[1] == ('drag', 40, 60, 70, 90, .5)
    if platform == 'android':
        assert mobile.calls[2][1] == 'gesture'
        assert mobile.calls[2][2][1:] == [
            {'x': 40, 'y': 60}, {'x': 70, 'y': 90}, {'x': 20, 'y': 40}, {'x': 90, 'y': 110}, 100]
    else:
        assert mobile.calls[2][1:3] == ('POST', '/actions')
        assert len(mobile.calls[2][3]['actions']) == 2
        assert all(pointer['actions'][-1]['type'] == 'pointerUp' for pointer in mobile.calls[2][3]['actions'])


def test_rotated_frame_maps_to_device_points(mobile):
    with _session(mobile, 'ios') as session:
        frame = session.capture()
        assert frame.orientation == 90
        assert frame.pixel_to_point((200, 100)) == (100, 50)
        rotated = frame.rotated(90)
        click_point = rotated.pixel_to_point((199, 200))
        expected_device_point = (100, 50)
        assert click_point == expected_device_point
        session.perform(mobile.api.Gesture('tap', (click_point,)))
    assert mobile.calls == [('tap', 100, 50)]


def test_mobile_pipeline_uses_device_frame(mobile, monkeypatch, tmp_path):
    from je_auto_control.utils.self_healing.frame_strategies import TemplateFrameStrategy, VLMFrameStrategy
    from je_auto_control.utils.self_healing.evaluation_models import LocatorPrediction
    from je_auto_control.utils.self_healing.heal_log import HealEventLog
    from je_auto_control.utils.self_healing.locator import self_heal_click
    from je_auto_control.wrapper import auto_control_image, auto_control_mouse
    captures = []
    desktop = []
    monkeypatch.setattr(auto_control_image, 'locate_image_center',
                        lambda *a, **k: desktop.append('capture') or (200, 100))
    monkeypatch.setattr(auto_control_mouse, 'set_mouse_position', lambda *a, **k: desktop.append('move'))
    monkeypatch.setattr(auto_control_mouse, 'click_mouse', lambda *a, **k: desktop.append('click'))
    monkeypatch.setattr(TemplateFrameStrategy, 'locate',
                        lambda self, sample: captures.append(sample.frame) or LocatorPrediction(None))
    monkeypatch.setattr(VLMFrameStrategy, 'locate',
                        lambda self, sample: captures.append(sample.frame) or LocatorPrediction((200, 100), 'vlm'))
    template = tmp_path / 'button.png'
    mobile.image.save(template)
    with _session(mobile, 'ios') as session, session.bind():
        result = self_heal_click(str(template), 'save', log=HealEventLog(str(tmp_path / 'heal.jsonl')))
    assert result.coordinates == (100, 50)
    assert mobile.calls == [('tap', 100, 50)]
    assert captures[0] == captures[1]
    assert mobile.capture_calls == ['device']
    desktop_capture_calls = len(desktop)
    assert desktop_capture_calls == 0


def test_adb_rejects_unicode_before_native_input(monkeypatch):
    from je_auto_control.android.adb_client import AdbClient, AdbError
    calls = []
    client = AdbClient(adb_path='fake-adb')
    monkeypatch.setattr(client, 'shell', lambda *a, **k: calls.append(a))
    with pytest.raises(AdbError, match='Unicode'):
        client.text('測試 café 🙂')
    assert calls == []


def test_frame_ocr_consumes_captured_bytes(mobile):
    from je_auto_control.utils.ocr.ocr_engine import TextMatch
    images = []
    backend = SimpleNamespace(image_to_matches=lambda image, lang, confidence:
                              images.append(image.size) or [TextMatch('Save', 20, 40, 20, 20, 99)])
    with _session(mobile, 'ios') as session:
        frame = session.capture()
        matches = frame.ocr(backend=backend)
        assert frame.pixel_to_point(matches[0].center) == (15, 25)
    assert images == [(600, 300)]


def test_invalid_gesture_and_closed_session_do_not_input(mobile):
    api = mobile.api
    with pytest.raises(api.DeviceSessionError):
        api.Gesture('drag', ((1, 2),))
    session = _session(mobile)
    session.cancel()
    with pytest.raises(api.DeviceSessionError):
        session.type_text('secret')
    assert mobile.calls == []


@pytest.mark.parametrize('degrees,pixel', [(0, (200, 100)), (90, (199, 200)),
                                          (180, (399, 199)), (270, (100, 399))])
def test_all_display_rotations_preserve_native_coordinates(mobile, degrees, pixel):
    with _session(mobile, 'ios') as session:
        frame = session.capture().rotated(degrees)
    assert frame.pixel_to_point(pixel) == (100, 50)


def test_orientation_change_and_bad_viewport_fail_without_input(mobile, monkeypatch):
    errors = mobile.api.DeviceSessionError
    with _session(mobile, 'ios') as session:
        sizes = iter([(300, 150), (150, 300)])
        monkeypatch.setattr(mobile.handle, '_unsafe_window_size', lambda: next(sizes))
        with pytest.raises(errors, match='geometry changed'):
            session.capture()
        monkeypatch.setattr(mobile.handle, '_unsafe_window_size', lambda: (150, 300))
        with pytest.raises(errors, match='aspect ratio'):
            session.capture()
    assert mobile.calls == []


def test_unsupported_sdk_capture_is_typed_and_has_no_fallback(mobile, monkeypatch):
    class SDKError(Exception):
        pass

    def fail():
        raise SDKError('geometry unavailable')

    monkeypatch.setattr(mobile.handle, '_unsafe_window_size', fail)
    with _session(mobile, 'ios') as session:
        with pytest.raises(mobile.api.DeviceSessionError) as caught:
            session.capture()
    assert isinstance(caught.value.__cause__, SDKError)
    assert mobile.capture_calls == []
    assert mobile.calls == []


def test_json_actions_mcp_builder_and_masking_share_mobile_operations(mobile, tmp_path):
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.executor.action_redaction import describe_action
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    for suffix in ('capture', 'gesture', 'type_text'):
        command = f'AC_mobile_{suffix}'
        function = getattr(mobile.api, f'mobile_{suffix}')
        assert executor.event_dict[command] is function
        assert tools[f'ac_mobile_{suffix}'].handler is function
        assert command in COMMAND_SPECS
    with _session(mobile, 'ios') as session, session.bind():
        geometry = mobile.api.mobile_capture(str(tmp_path / 'phone.png'))
        mobile.api.mobile_gesture({'kind': 'tap', 'points': [[100, 50]]})
        assert mobile.api.mobile_type_text('測試 café 🙂') is None
        with pytest.raises(mobile.api.DeviceSessionError, match='match'):
            mobile.api.mobile_type_text('wrong device', {'platform': 'android', 'serial': 'other'})
    assert geometry['pixel_size'] == [600, 300]
    assert geometry['point_size'] == [300, 150]
    assert (tmp_path / 'phone.png').read_bytes().startswith(b'\x89PNG')
    assert mobile.calls == [('tap', 100, 50), ('text', '測試 café 🙂')]
    assert '測試' not in describe_action(['AC_mobile_type_text', {'text': '測試 café 🙂'}])
    assert '測試' not in describe_action(['AC_mobile_type_text', ['測試 café 🙂']])
    from je_auto_control.utils.action_journal.privacy import private_input, secret_values
    arguments = ['測試 café 🙂', {'platform': 'ios', 'url': 'http://127.0.0.1:8100'}]
    masked, reasons = private_input('AC_mobile_type_text', arguments)
    assert masked == ['***', arguments[1]]
    assert reasons
    assert secret_values('AC_mobile_type_text', arguments, arguments) == {'測試 café 🙂'}


@pytest.mark.parametrize('gesture', [None, [], {'kind': []}, {'kind': 'tap', 'points': [[True, 2]]},
                                   {'kind': 'tap', 'points': [[1, 2]], 'extra': True}])
def test_malformed_json_gesture_rejected_before_native_input(mobile, gesture):
    with pytest.raises(mobile.api.DeviceSessionError):
        mobile.api.mobile_gesture(gesture, {'platform': 'android', 'serial': 'phone-a'})
    assert mobile.calls == []


def test_rotation_after_locator_rejects_stale_touch(mobile, monkeypatch, tmp_path):
    from je_auto_control.utils.self_healing.frame_strategies import VLMFrameStrategy
    from je_auto_control.utils.self_healing.evaluation_models import LocatorPrediction
    from je_auto_control.utils.self_healing.heal_log import HealEventLog
    from je_auto_control.utils.self_healing.locator import self_heal_click

    def locate(self, sample):
        mobile.handle.orientation = 'PORTRAIT'
        return LocatorPrediction((200, 100), 'vlm')

    monkeypatch.setattr(VLMFrameStrategy, 'locate', locate)
    with _session(mobile, 'ios') as session, session.bind():
        with pytest.raises(mobile.api.DeviceSessionError, match='geometry changed'):
            self_heal_click(description='save', log=HealEventLog(str(tmp_path / 'heal.jsonl')))
    assert mobile.calls == []
