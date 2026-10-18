"""Unbound VLM calls use injected logical geometry, never native capture or a network."""
import io

import pytest
from PIL import Image

from je_auto_control.utils.vision import vlm_api
from je_auto_control.utils.vision.backends.base import VLMBackend
from je_auto_control.utils.vision.backends.base import VLMRequestError


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("native capture is not authorized in this test")

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame._load_image_grab", forbidden)
    monkeypatch.setattr("je_auto_control.utils.cv2_utils.region_capture.grab_screen_region", forbidden)


class Backend(VLMBackend):
    available, name = True, "controlled"

    def __init__(self):
        self.images = []

    def locate(self, image_bytes, description, model=None, image_mime="image/png"):
        self.images.append(image_bytes)
        return 3, 4


def test_unbound_origin_comes_from_actual_logical_capture(monkeypatch):
    calls = []

    def grab(region=None, **kwargs):
        calls.append((region, kwargs["all_screens"]))
        return Image.new("RGB", (20, 10)), -80, -40

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical", grab)
    bound = Backend()
    assert vlm_api.locate_by_description("submit", backend=bound) == (-77, -36)
    assert calls == [(None, False)]
    with Image.open(io.BytesIO(bound.images[0])) as frame:
        assert frame.size == (20, 10)


def test_unbound_region_uses_actual_clipped_origin(monkeypatch):
    def grab(region, **_kwargs):
        assert region == (-100, -60, 30, 30)
        return Image.new("RGB", (10, 10)), -80, -40

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical", grab)
    assert vlm_api.locate_by_description("submit", [-100, -60, -70, -30], backend=Backend()) == (-77, -36)


def test_unbound_retina_frame_is_downscaled_before_backend(monkeypatch):
    from je_auto_control.utils.monitor_layout import logical_frame
    original = logical_frame.grab_logical
    calls = []

    class Grabber:
        @staticmethod
        def grab(**kwargs):
            calls.append(kwargs)
            left, top, right, bottom = kwargs["bbox"]
            return Image.new("RGB", ((right - left) * 2, (bottom - top) * 2))

    monkeypatch.setattr(logical_frame, "grab_logical", lambda region=None, **kwargs: original(
        region, **kwargs, grabber=Grabber(), displays=lambda: [(0, 0, 20, 10), (-20, 0, 20, 10)]))
    bound = Backend()
    assert vlm_api.locate_by_description("submit", [-22, 0, -10, 10], backend=bound) == (-17, 4)
    assert calls == [{"bbox": (-20, 0, -10, 10), "scale_down": True}]
    with Image.open(io.BytesIO(bound.images[0])) as frame:
        assert frame.size == (10, 10)


def test_geometry_scope_resets_on_nested_reads_and_errors(monkeypatch):
    from je_auto_control.utils.vision.frame_capture import capture_png, capture_with_geometry

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical",
                        lambda *_a, **_k: (Image.new("RGB", (8, 8)), -10, -20))

    def reader(region):
        data = capture_png(region)
        assert capture_with_geometry(lambda _: b"legacy", None) == (b"legacy", None)
        return data

    data, frame = capture_with_geometry(reader, None)
    assert frame.origin == (-10, -20) and frame.png == data

    def fail(region):
        capture_png(region)
        raise RuntimeError("controlled capture error")

    with pytest.raises(RuntimeError):
        capture_with_geometry(fail, None)
    assert capture_with_geometry(lambda _: b"legacy", None) == (b"legacy", None)


def test_altered_reader_bytes_cannot_reuse_other_geometry(monkeypatch):
    from je_auto_control.utils.vision.frame_capture import capture_png, capture_with_geometry

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical",
                        lambda *_a, **_k: (Image.new("RGB", (8, 8)), -10, -20))

    def reader(region):
        capture_png(region)
        return b"altered"

    with pytest.raises(VLMRequestError, match="geometry"):
        capture_with_geometry(reader, None)


def test_callback_isolates_parent_frame_and_restores_it(monkeypatch):
    from je_auto_control.utils.cv2_utils.locator_frame import current_locator_frame, locator_frame_scope
    from je_auto_control.utils.self_healing import VerificationRequest
    from je_auto_control.utils.self_healing.verification import prepare_verification

    captures = []

    def grab(*_args, **_kwargs):
        captures.append(len(captures))
        return Image.new("RGB", (8, 8)), len(captures) * 10, 0

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical", grab)
    with locator_frame_scope(None, all_screens=False) as parent:
        assert parent.snapshot().origin == (10, 0)

        def callback():
            assert current_locator_frame() is None
            return vlm_api.locate_by_description("fresh", backend=Backend()) == (23, 4)

        proof = prepare_verification(VerificationRequest(verifier=callback), None)()
        assert proof.verified and proof.frame_hash is None
        assert current_locator_frame() is parent and parent.snapshot().origin == (10, 0)
    assert len(captures) == 2 and current_locator_frame() is None
