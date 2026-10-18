"""Framework assertions may not be healed, formatted or followed by mouse input."""
import pytest

from je_auto_control.utils.exception.exceptions import AutoControlAssertionException
from je_auto_control.utils.self_healing import HealEventLog, self_heal_click, self_heal_locate


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("assertion recovery tests must not capture a desktop")

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame._load_image_grab", forbidden)
    monkeypatch.setattr("je_auto_control.utils.cv2_utils.region_capture.grab_screen_region", forbidden)


class AssertionSignal(AutoControlAssertionException):
    def __str__(self):
        pytest.fail("a control assertion must not be formatted as an ordinary miss")


@pytest.mark.parametrize("entry", [self_heal_locate, self_heal_click])
@pytest.mark.parametrize("strategy", ["image", "vlm"])
def test_assertion_propagates_exactly_before_fallback_or_click(monkeypatch, tmp_path, entry, strategy):
    signal = AssertionSignal("controlled assertion")
    calls = []

    def image(*_args, **_kwargs):
        calls.append("image")
        if strategy == "image":
            raise signal
        from je_auto_control.utils.exception.exceptions import ImageNotFoundException
        raise ImageNotFoundException("missing")

    def vlm(*_args, **_kwargs):
        calls.append("vlm")
        if strategy == "vlm":
            raise signal
        return 1, 2

    monkeypatch.setattr("je_auto_control.wrapper.auto_control_image.locate_image_center", image)
    monkeypatch.setattr("je_auto_control.utils.vision.vlm_api.locate_by_description", vlm)
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", lambda *_: calls.append("click"))
    log = HealEventLog(tmp_path / "events.jsonl")
    with pytest.raises(AutoControlAssertionException) as caught:
        entry("unused.png", "submit", log=log)
    assert caught.value is signal
    assert calls == (["image"] if strategy == "image" else ["image", "vlm"])
    assert not log.path.exists()
