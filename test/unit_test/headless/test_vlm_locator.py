"""Tests for the VLM-based element locator API."""
from typing import Optional, Tuple

import pytest

from je_auto_control.utils.vision import backends as backends_mod
from je_auto_control.utils.vision.backends._parse import (
    LOCATE_PROMPT, parse_coords,
)
from je_auto_control.utils.vision.backends.base import (
    VLMBackend, VLMNotAvailableError,
)
from je_auto_control.utils.vision.backends.null_backend import NullVLMBackend
from je_auto_control.utils.vision.vlm_api import (
    click_by_description, locate_by_description,
)


class _FakeBackend(VLMBackend):
    name = "fake"
    available = True

    def __init__(self, coords: Optional[Tuple[int, int]]) -> None:
        self._coords = coords
        self.last_call: Optional[dict] = None

    def locate(self, image_bytes: bytes, description: str,
               model: Optional[str] = None,
               image_mime: str = "image/png",
               ) -> Optional[Tuple[int, int]]:
        self.last_call = {
            "bytes_len": len(image_bytes),
            "description": description,
            "model": model,
            "image_mime": image_mime,
        }
        return self._coords


@pytest.fixture
def stub_screenshot(monkeypatch):
    """Make ``_capture_screenshot_bytes`` return a fixed byte payload."""
    from je_auto_control.utils.vision import vlm_api

    def fake_capture(screen_region=None):
        return b"fake-png-bytes"

    monkeypatch.setattr(vlm_api, "_capture_screenshot_bytes", fake_capture)


def test_parse_coords_accepts_plain_pair():
    assert parse_coords("120,45") == (120, 45)


def test_parse_coords_tolerates_whitespace_and_prose():
    assert parse_coords("The button is at 300, 400 pixels.") == (300, 400)


def test_parse_coords_returns_none_for_sentinels():
    assert parse_coords("none") is None
    assert parse_coords("Not Found") is None
    assert parse_coords("n/a") is None
    assert parse_coords("") is None


def test_parse_coords_returns_none_when_no_pair_present():
    assert parse_coords("sorry, I cannot see it") is None


def test_locate_prompt_embeds_description():
    msg = LOCATE_PROMPT.format(description="green Submit button")
    assert "green Submit button" in msg
    assert "x,y" in msg


def test_null_backend_raises_with_custom_reason():
    backend = NullVLMBackend("sdk not installed")
    assert backend.available is False
    with pytest.raises(VLMNotAvailableError) as info:
        backend.locate(b"", "desc")
    assert "sdk not installed" in str(info.value)


def test_reset_backend_cache_clears_cached_instance():
    backends_mod._cached_backend = _FakeBackend((1, 2))
    assert backends_mod.get_backend() is backends_mod._cached_backend
    backends_mod.reset_backend_cache()
    assert backends_mod._cached_backend is None


def test_locate_raises_when_backend_unavailable(stub_screenshot):
    with pytest.raises(VLMNotAvailableError):
        locate_by_description("anything", backend=NullVLMBackend("nope"))


def test_locate_requires_non_empty_description():
    with pytest.raises(ValueError):
        locate_by_description("   ", backend=_FakeBackend((0, 0)))


def test_locate_returns_backend_coords(stub_screenshot):
    fake = _FakeBackend((150, 275))
    assert locate_by_description("btn", backend=fake) == (150, 275)
    assert fake.last_call["description"] == "btn"
    assert fake.last_call["bytes_len"] == len(b"fake-png-bytes")


def test_locate_returns_none_when_backend_says_none(stub_screenshot):
    assert locate_by_description("btn", backend=_FakeBackend(None)) is None


def test_locate_translates_region_to_absolute_coords(stub_screenshot):
    fake = _FakeBackend((20, 30))
    result = locate_by_description(
        "btn", screen_region=[100, 200, 400, 500], backend=fake,
    )
    assert result == (120, 230)


def test_locate_forwards_model_override(stub_screenshot):
    fake = _FakeBackend((1, 1))
    locate_by_description("btn", model="claude-opus-4-7", backend=fake)
    assert fake.last_call["model"] == "claude-opus-4-7"


def test_click_returns_false_when_not_found(stub_screenshot):
    assert click_by_description("btn", backend=_FakeBackend(None)) is False


def test_executor_registers_vlm_commands():
    from je_auto_control.utils.executor.action_executor import executor
    commands = executor.known_commands()
    assert "AC_vlm_locate" in commands
    assert "AC_vlm_click" in commands


def test_package_facade_exports_vlm_api():
    import je_auto_control as ac
    assert hasattr(ac, "VLMNotAvailableError")
    assert hasattr(ac, "locate_by_description")
    assert hasattr(ac, "click_by_description")
