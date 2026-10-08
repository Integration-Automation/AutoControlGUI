"""Mobile text, gestures, frames and locating, against the fake backends.

No device is involved: these prove which commands are sent and how frame
pixels map to input coordinates, not that a phone reacts to them.
"""
import io

import pytest
from PIL import Image

from headless._mobile_doubles import (
    ADB_KEYBOARD_IME, FakeAdbHost, FakeU2, FakeWda, png_bytes,
)
from je_auto_control.android import AdbClient, UIAutomatorDevice
from je_auto_control.ios import IOSDevice
from je_auto_control.utils.exception.exceptions import ImageNotFoundException
from je_auto_control.utils.ocr.ocr_engine import TextMatch
from je_auto_control.utils.self_healing.locator import self_heal_locate
from je_auto_control.wrapper.device_context import (
    DeviceContext, DeviceError, DeviceUnsupportedError, Drag, LongPress, Pinch,
    Swipe, Tap, open_device,
)
from je_auto_control.wrapper.device_frame import DeviceFrame

UNICODE_TEXT = "測試 café 🙂"


@pytest.fixture
def adb_host(monkeypatch):
    """A fake ADB host with one attached device, ``phone``."""
    host = FakeAdbHost()
    host.add("phone")
    monkeypatch.setattr("je_auto_control.android.adb_client.subprocess.run", host.run)
    from je_auto_control.utils.executor import action_executor
    monkeypatch.setattr(action_executor, "_android_client_cache", {})
    return host


@pytest.fixture
def no_uiautomator(monkeypatch):
    """Pretend uiautomator2 is not installed, whatever the host has."""
    monkeypatch.setattr("je_auto_control.android.input.find_spec", lambda _name: None)
    monkeypatch.setattr("je_auto_control.android.session.find_spec", lambda _name: None)


def _android(host, **transports):
    return open_device(DeviceContext("android", "phone", adb_path="fake-adb"), **transports)


def _ios(handle):
    return open_device(DeviceContext("ios", "http://wda.test:8100"),
                       device=IOSDevice(url="http://wda.test:8100", handle=handle))


# --- text --------------------------------------------------------------

def test_unicode_round_trip(adb_host, no_uiautomator):
    phone = adb_host.devices["phone"]
    phone.ime = ADB_KEYBOARD_IME
    _android(adb_host).type_text(UNICODE_TEXT)
    received_text = phone.typed[-1]
    assert received_text == '測試 café 🙂'
    # It did not go through the path that would have dropped it.
    assert not any(command.startswith("input text") for command in phone.shell_commands)


def test_ascii_still_uses_input_text(adb_host, no_uiautomator):
    phone = adb_host.devices["phone"]
    _android(adb_host).type_text("hello world")
    assert phone.typed == ["hello world"]
    assert "input text hello%sworld" in phone.shell_commands


def test_unicode_goes_to_uiautomator_without_the_ime(adb_host):
    handle = FakeU2()
    _android(adb_host, ui_device=UIAutomatorDevice(handle=handle)).type_text(UNICODE_TEXT)
    assert handle.typed == [UNICODE_TEXT]
    assert adb_host.devices["phone"].typed == []


@pytest.mark.parametrize("text", [UNICODE_TEXT, "100%s done"])
def test_text_no_path_can_carry_is_refused_not_sent(adb_host, no_uiautomator, text):
    phone = adb_host.devices["phone"]
    with pytest.raises(DeviceUnsupportedError) as caught:
        _android(adb_host).type_text(text)
    assert caught.value.alternative
    assert phone.input_calls == []
    assert phone.typed == []
    # The low-level method refuses it too, instead of reporting success.
    with pytest.raises(DeviceUnsupportedError):
        AdbClient(adb_path="fake-adb", default_serial="phone").text(text)
    assert phone.input_calls == []


def test_executor_text_command_carries_unicode(adb_host, no_uiautomator):
    from je_auto_control.utils.executor.action_executor import executor
    phone = adb_host.devices["phone"]
    phone.ime = ADB_KEYBOARD_IME
    executor.event_dict["AC_android_text"](UNICODE_TEXT, serial="phone", adb_path="fake-adb")
    assert phone.typed == [UNICODE_TEXT]


def test_ios_text_is_sent_whole():
    handle = FakeWda()
    _ios(handle).type_text(UNICODE_TEXT)
    assert handle.typed == [UNICODE_TEXT]


# --- gestures ----------------------------------------------------------

def test_long_press_drag_pinch(adb_host):
    phone = adb_host.devices["phone"]
    handle = FakeU2()
    session = _android(adb_host, ui_device=UIAutomatorDevice(handle=handle))
    session.perform(Tap(5, 6))
    session.perform(LongPress(10, 20, duration_s=1.5))
    session.perform(Swipe(1, 2, 3, 4, duration_s=0.2))
    session.perform(Drag(10, 20, 300, 400, hold_s=0.5, duration_s=0.5))
    session.perform(Pinch(500, 800, scale=2.0, duration_s=0.5, span=400))
    assert phone.input_calls == [
        "input tap 5 6",
        "input swipe 10 20 10 20 1500",
        "input swipe 1 2 3 4 200",
        "input draganddrop 10 20 300 400 1000",
    ]
    # Zooming in: the fingers start close and end `span` apart, about the centre.
    assert handle.calls == [{"op": "gesture", "start1": (400, 800), "start2": (600, 800),
                             "end1": (300, 800), "end2": (700, 800), "steps": 100}]


def test_pinch_out_closes_the_fingers(adb_host):
    handle = FakeU2()
    session = _android(adb_host, ui_device=UIAutomatorDevice(handle=handle))
    session.perform(Pinch(500, 800, scale=0.5, span=400))
    assert handle.calls[0]["start1"] == (300, 800)
    assert handle.calls[0]["end1"] == (400, 800)


def test_drag_falls_back_when_input_lacks_draganddrop(adb_host, no_uiautomator):
    phone = adb_host.devices["phone"]
    phone.has_draganddrop = False
    handle = FakeU2()
    _android(adb_host, ui_device=UIAutomatorDevice(handle=handle)).perform(
        Drag(1, 2, 3, 4, hold_s=0.25, duration_s=0.25))
    assert handle.calls == [{"op": "drag", "sx": 1, "sy": 2, "ex": 3, "ey": 4,
                             "duration": 0.5}]
    # With no fallback, the usage text `input` printed is an error, not a success.
    with pytest.raises(DeviceUnsupportedError):
        _android(adb_host).perform(Drag(1, 2, 3, 4))


def test_pinch_without_multi_touch_says_why(adb_host, no_uiautomator):
    with pytest.raises(DeviceUnsupportedError) as caught:
        _android(adb_host).perform(Pinch(1, 2, scale=2.0))
    assert "uiautomator2" in caught.value.alternative
    assert adb_host.devices["phone"].input_calls == []


def test_ios_gestures():
    handle = FakeWda()
    session = _ios(handle)
    session.perform(LongPress(10, 20, duration_s=1.5))
    session.perform(Drag(1, 2, 3, 4, hold_s=0.75))
    session.perform(Pinch(0, 0, scale=0.5, duration_s=0.5))
    session.press_key("home")
    assert handle.input_calls == [
        {"op": "tap_hold", "x": 10, "y": 20, "duration": 1.5},
        {"op": "swipe", "x1": 1, "y1": 2, "x2": 3, "y2": 4, "duration": 0.75},
        {"op": "pinch", "scale": 0.5, "velocity": -1.0},
        {"op": "press", "name": "home"},
    ]


def test_invalid_gestures_are_rejected():
    with pytest.raises(DeviceError):
        Pinch(1, 2, scale=1)
    with pytest.raises(DeviceError):
        LongPress(1, 2, duration_s=-1)


# --- frames ------------------------------------------------------------

def _upright_with_patch(size, patch):
    return Image.open(io.BytesIO(png_bytes(size[0], size[1], patch=patch)))


def _as_png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_rotated_frame_maps_to_device_points():
    # An iPhone held in landscape: 844x390 points, 3 pixels per point. This WDA
    # build returns the panel's portrait buffer, so the screenshot is 1170x2532.
    upright = _upright_with_patch((2532, 1170), (600, 810, 90, 60))
    template = upright.crop((600, 810, 690, 870))
    raw = upright.rotate(-90, expand=True)
    assert raw.size == (1170, 2532)
    handle = FakeWda(points=(390, 844), scale=3, orientation="LANDSCAPE")
    handle.screen = _as_png(raw)
    session = _ios(handle)
    frame = session.capture()
    assert frame.pixel_size == (2532, 1170)
    assert frame.point_size == (844, 390)
    assert frame.orientation == "landscape_left"
    # Patch centre (645, 840) px upright -> (215, 280) points.
    expected_device_point = (215, 280)
    click_point = frame.locate_image(template)
    session.perform(Tap(*click_point))
    assert click_point == expected_device_point
    assert handle.input_calls == [{"op": "tap", "x": 215, "y": 280}]


def test_retina_pixels_are_not_tapped_as_points():
    handle = FakeWda(points=(390, 844), scale=3)
    frame = _ios(handle).capture()
    assert frame.scale == 3
    assert frame.pixel_to_point(600, 1500) == (200, 500)
    assert frame.point_to_pixel(200, 500) == (600, 1500)
    with pytest.raises(DeviceError):
        frame.pixel_to_point(1170, 0)


def test_android_frame_follows_the_display_rotation(adb_host):
    phone = adb_host.devices["phone"]
    phone.rotation = 1
    frame = _android(adb_host).capture()
    # screencap already comes back in landscape: pixels are the tap coordinates.
    assert frame.pixel_size == (1920, 1080)
    assert frame.point_size == (1920, 1080)
    assert frame.orientation == "landscape_left"
    assert frame.pixel_to_point(1500, 900) == (1500, 900)
    # A device that returns the natural portrait buffer instead is turned upright.
    upright = _upright_with_patch((1920, 1080), (300, 200, 90, 60))
    phone.screen = _as_png(upright.rotate(-90, expand=True))
    turned = _android(adb_host).capture()
    assert turned.pixel_size == (1920, 1080)
    assert turned.locate_image(upright.crop((300, 200, 390, 260))) == (345, 230)
    # Reading the geometry sent no input.
    assert phone.input_calls == []


def test_template_absent_from_the_frame_is_not_found(adb_host):
    frame = _android(adb_host).capture()
    template = _upright_with_patch((90, 60), (0, 0, 90, 60))
    with pytest.raises(ImageNotFoundException):
        frame.locate_image(template)


# --- the locating pipeline never looks at the host's desktop ------------

class _FakeOcr:
    name = "fake"
    available = True

    def image_to_matches(self, image, lang, min_confidence):
        self.seen = image.size
        return [TextMatch("Sign", 600, 300, 60, 30, 99.0),
                TextMatch("in", 666, 300, 30, 30, 99.0)]


class _FakeVlm:
    name = "fake"
    available = True

    def __init__(self, reply):
        self.reply = reply
        self.images = []

    def locate(self, image_bytes, description, model=None, image_mime="image/png"):
        self.images.append(Image.open(io.BytesIO(image_bytes)).size)
        return self.reply


def test_mobile_pipeline_uses_device_frame(monkeypatch, tmp_path):
    desktop = []

    def touched(name):
        def record(*_args, **_kwargs):
            desktop.append(name)
            raise AssertionError(f"the desktop was used: {name}")
        return record

    for target in (
            "je_auto_control.utils.monitor_layout.logical_frame.grab_logical",
            "je_auto_control.utils.ocr.ocr_engine.grab_logical",
            "je_auto_control.utils.cv2_utils.template_detection.grab_logical",
            "je_auto_control.utils.vision.vlm_api._capture_screenshot_bytes",
            "je_auto_control.wrapper.auto_control_mouse.click_mouse",
            "je_auto_control.wrapper.auto_control_mouse.set_mouse_position"):
        monkeypatch.setattr(target, touched(target))
    vlm = _FakeVlm((900, 600))
    monkeypatch.setattr("je_auto_control.utils.vision.backends.get_backend", lambda: vlm)

    handle = FakeWda(points=(390, 844), scale=3)
    handle.screen = png_bytes(1170, 2532, patch=(300, 900, 90, 60))
    session = _ios(handle)
    frame = session.capture()
    template = tmp_path / "button.png"
    frame.image.crop((300, 900, 390, 960)).save(template)
    missing = tmp_path / "absent.png"
    Image.open(io.BytesIO(png_bytes(40, 40, color=(200, 30, 30),
                                    patch=(5, 5, 30, 30)))).save(missing)

    ocr = _FakeOcr()
    assert frame.locate_image(str(template)) == (115, 310)
    assert frame.locate_text("Sign in", backend=ocr) == (216, 105)
    assert ocr.seen == (1170, 2532)
    assert frame.locate_description("the blue button") == (300, 200)
    assert vlm.images == [(1170, 2532)]

    from je_auto_control.utils.self_healing.heal_log import HealEventLog
    log = HealEventLog(str(tmp_path / "heal.jsonl"))
    hit = self_heal_locate(template_path=str(template), frame=frame, log=log)
    healed = self_heal_locate(template_path=str(missing), description="the blue button",
                              frame=frame, log=log)
    assert (hit.method, hit.coordinates) == ("image", (115, 310))
    assert (healed.method, healed.coordinates) == ("vlm", (300, 200))
    session.perform(Tap(*healed.coordinates))

    desktop_capture_calls = len(desktop)
    assert desktop_capture_calls == 0
    assert handle.input_calls == [{"op": "tap", "x": 300, "y": 200}]


def test_vlm_reply_off_the_frame_is_not_a_location():
    frame = DeviceFrame(image=Image.new("RGB", (300, 600)), point_size=(100, 200))
    assert frame.locate_description("x", backend=_FakeVlm((300, 10))) is None
    assert frame.locate_description("x", backend=_FakeVlm(None)) is None
