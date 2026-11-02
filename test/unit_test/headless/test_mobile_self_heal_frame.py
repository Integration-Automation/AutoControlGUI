"""The mobile self-heal searches the device's own frame, never the host's screen.

The desktop locator searches the screen of the machine AutoControl runs on, so a
device session cannot use it; ``_self_heal`` runs the same order -- template
first, the VLM on a miss -- against ``session.capture()``.
"""
import pytest

from je_auto_control.utils.exception.exceptions import ImageNotFoundException
from je_auto_control.wrapper import mobile_commands


class _Frame:
    def __init__(self, image=None, vlm=None, vlm_error=None):
        self._image, self._vlm, self._vlm_error = image, vlm, vlm_error
        self.calls = []

    def locate_image(self, template, threshold):
        self.calls.append(("image", template, threshold))
        if self._image is None:
            raise ImageNotFoundException("no match in the device frame")
        return self._image

    def locate_description(self, description, *, model=None):
        self.calls.append(("vlm", description, model))
        if self._vlm_error is not None:
            raise self._vlm_error
        return self._vlm


class _Session:
    def __init__(self, frame):
        self.frame = frame
        self.performed = []

    def capture(self):
        return self.frame

    def perform(self, gesture):
        self.performed.append(gesture)


@pytest.fixture(autouse=True)
def _no_desktop(monkeypatch):
    from je_auto_control.utils.self_healing import locator

    def refuse(*_args, **_kwargs):
        raise AssertionError("the desktop locator was called for a device")
    monkeypatch.setattr(locator, "self_heal_locate", refuse)


def test_a_template_hit_in_the_frame_is_the_answer_and_the_vlm_is_not_asked():
    frame = _Frame(image=(40, 60), vlm=(1, 1))
    result = mobile_commands._self_heal(_Session(frame), template_path="ok.png",
                                        description="the OK button")
    assert result["found"] is True
    assert result["method"] == "image"
    assert result["coordinates"] == [40, 60]
    assert frame.calls == [("image", "ok.png", 0.9)]


def test_a_template_miss_falls_back_to_the_vlm_on_the_same_frame():
    frame = _Frame(vlm=(7, 8))
    session = _Session(frame)
    result = mobile_commands._self_heal(session, template_path="ok.png",
                                        description="the OK button", model="m", tap=True)
    assert (result["found"], result["method"], result["coordinates"]) == (True, "vlm", [7, 8])
    assert "no match" in result["image_error"]
    assert [call[0] for call in frame.calls] == ["image", "vlm"]
    assert len(session.performed) == 1, "tap=True taps the healed point on the device"


def test_a_miss_on_both_reports_each_reason_and_taps_nothing():
    frame = _Frame(vlm_error=RuntimeError("model offline"))
    session = _Session(frame)
    result = mobile_commands._self_heal(session, template_path="ok.png",
                                        description="the OK button", tap=True)
    assert (result["found"], result["method"], result["coordinates"]) == (False, "miss", None)
    assert "no match" in result["image_error"]
    assert "model offline" in result["vlm_error"]
    assert session.performed == []


def test_neither_a_template_nor_a_description_is_refused():
    session = _Session(_Frame())
    with pytest.raises(ValueError):
        mobile_commands._self_heal(session)
