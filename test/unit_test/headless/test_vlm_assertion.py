"""Tests for the VLM natural-language assertion (assert_by_description)."""
import pytest

from je_auto_control.utils.assertion.assertions import assert_by_description
from je_auto_control.utils.exception.exceptions import (
    AutoControlAssertionException,
)
from je_auto_control.utils.vision import vlm_api
from je_auto_control.utils.vision.backends.base import (
    VLMBackend, VLMNotAvailableError,
)


class _FakeBackend(VLMBackend):
    """Controllable backend: ``locate`` returns coords iff ``verdict``."""

    available = True

    def __init__(self, verdict: bool = True) -> None:
        self._verdict = verdict

    def locate(self, image_bytes, description, model=None,
               image_mime="image/png"):
        return (1, 2) if self._verdict else None


@pytest.fixture(autouse=True)
def _no_real_screenshot(monkeypatch):
    monkeypatch.setattr(vlm_api, "_capture_screenshot_bytes",
                        lambda region=None: b"png-bytes")


def test_default_verify_delegates_to_locate():
    assert _FakeBackend(True).verify(b"x", "a button") is True
    assert _FakeBackend(False).verify(b"x", "a button") is False


def test_assert_passes_when_vlm_matches():
    result = assert_by_description("a login form", backend=_FakeBackend(True),
                                   raise_on_fail=False)
    assert result.passed is True
    assert result.kind == "vlm"


def test_assert_fails_and_raises_when_no_match():
    with pytest.raises(AutoControlAssertionException):
        assert_by_description("a login form", backend=_FakeBackend(False))


def test_assert_absence_passes_when_not_shown():
    result = assert_by_description(
        "an error dialog", present=False,
        backend=_FakeBackend(False), raise_on_fail=False,
    )
    assert result.passed is True


def test_raises_without_a_configured_backend():
    class _Unavailable(VLMBackend):
        available = False

        def locate(self, image_bytes, description, model=None,
                   image_mime="image/png"):
            return None

    with pytest.raises(VLMNotAvailableError):
        assert_by_description("anything", backend=_Unavailable(),
                              raise_on_fail=False)
