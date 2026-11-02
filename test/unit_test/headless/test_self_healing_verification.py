"""Explicit post-operation verification uses fresh controlled evidence, never native devices."""
from pathlib import Path
import asyncio
from concurrent.futures import CancelledError
from dataclasses import FrozenInstanceError
from hashlib import sha256

import pytest
from PIL import Image

import je_auto_control as ac
from je_auto_control.utils.self_healing import HealEventLog
from je_auto_control.utils.exception.exceptions import AutoControlAssertionException
from je_auto_control.utils.mcp_server.context import OperationCancelledError
from je_auto_control.utils.vision.backends.base import VLMBackend, VLMNotAvailableError, VLMRequestError

FIXTURES = Path(__file__).resolve().parents[3] / "benchmarks/self_healing/fixtures"


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("verification tests must not capture a desktop or issue native input")

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame._load_image_grab", forbidden)
    monkeypatch.setattr("je_auto_control.utils.cv2_utils.region_capture.grab_screen_region", forbidden)
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", forbidden)


def test_callback_runs_after_click_and_records_explicit_result(monkeypatch, tmp_path):
    from je_auto_control import SelfHealRequest, VerificationRequest, self_heal_run

    calls = []

    def grab(*_args, **_kwargs):
        calls.append("capture")
        with Image.open(FIXTURES / "frame_new.png") as image:
            return image.copy(), -80, -40

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical", grab)
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", lambda *_: calls.append("click"))
    log = HealEventLog(tmp_path / "events.jsonl")

    def verify():
        calls.append("verify")
        return True

    result = self_heal_run(SelfHealRequest(template_path=str(FIXTURES / "new.png"), log=log, operation="click",
                                           verification=VerificationRequest(verifier=verify)))
    assert calls == ["capture", "click", "verify"]
    assert result.verified is True and result.operation_status == "verified"
    event, = log.list_events()
    assert event.verified is True and event.verification_backend == "callback"


def test_request_validation_happens_before_any_effect():
    with pytest.raises(ac.SelfHealRequestError):
        ac.SelfHealRequest(description="submit", operation="locate",
                           verification=ac.VerificationRequest(verifier=lambda: True))


@pytest.fixture
def located(monkeypatch, tmp_path):
    calls = []
    log = HealEventLog(tmp_path / "events.jsonl")
    monkeypatch.setattr("je_auto_control.wrapper.auto_control_image.locate_image_center", lambda *_a, **_k: (2, 3))
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", lambda *_: calls.append("click"))
    return calls, log


@pytest.mark.parametrize("verdict", [True, False, None])
def test_explicit_verdict_and_unknown_remain_distinct(located, verdict):
    calls, log = located
    verification = None if verdict is None else ac.VerificationRequest(verifier=lambda: verdict)
    result = ac.self_heal_run(ac.SelfHealRequest(template_path="fake.png", operation="click", log=log,
                                                verification=verification))
    assert calls == ["click"]
    assert result.verified is verdict
    assert result.operation_status == {True: "verified", False: "verification_failed", None: "issued"}[verdict]
    event, = log.list_events()
    assert event.verified is verdict and event.operation_status == result.operation_status
    assert ("verify" in event.strategy_times_ms) == (verdict is not None)


class Verifier(VLMBackend):
    available, name = True, "controlled-verifier"

    def __init__(self, verdict=True):
        self.verdict, self.images, self.nested = verdict, [], []

    def locate(self, image_bytes, description, model=None, image_mime="image/png"):
        self.nested.append(image_bytes)
        return 1, 2

    def resolve_model(self, model=None):
        return model or "controlled-default"

    def verify(self, image_bytes, description, model=None, image_mime="image/png"):
        from je_auto_control.utils.vision.vlm_api import locate_by_description
        self.images.append((image_bytes, model))
        # A backend's nested visual helper must see the new frame, never the pre-click owner.
        assert locate_by_description("nested", backend=self) == (101, 202)
        return self.verdict


def test_vlm_verification_captures_after_click_and_shares_only_new_frame(monkeypatch, tmp_path):
    calls = []
    bound = Verifier()

    def grab(region=None, **kwargs):
        calls.append(("capture", region, kwargs["all_screens"]))
        if len(calls) == 1:
            with Image.open(FIXTURES / "frame_new.png") as image:
                return image.copy(), -80, -40
        assert calls[-2] == "click"
        return Image.new("RGB", (32, 16), "green"), 100, 200

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical", grab)
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", lambda *_: calls.append("click"))
    log = HealEventLog(tmp_path / "events.jsonl")
    result = ac.self_heal_run(ac.SelfHealRequest(
        template_path=str(FIXTURES / "new.png"), operation="click", model="chosen", log=log,
        verification=ac.VerificationRequest(description="done", backend=bound, screen_region=[100, 200, 132, 216])))
    assert calls == [("capture", None, True), "click", ("capture", (100, 200, 32, 16), False)]
    assert bound.nested == [bound.images[0][0]] and bound.images[0][1] == "chosen"
    assert result.verified is True and result.verification_model == "chosen"
    event, = log.list_events()
    assert event.verification_frame_hash == sha256(bound.images[0][0]).hexdigest()
    assert event.frame_hash != event.verification_frame_hash
    assert event.verification_description == "done" and event.verification_backend == "controlled-verifier"


def test_unavailable_verifier_refuses_before_locate_or_input(located, monkeypatch):
    calls, log = located
    monkeypatch.setattr("je_auto_control.wrapper.auto_control_image.locate_image_center",
                        lambda *_a, **_k: pytest.fail("must preflight before locating"))
    bound = Verifier()
    bound.available = False
    with pytest.raises(VLMNotAvailableError):
        ac.self_heal_run(ac.SelfHealRequest(template_path="fake.png", operation="click", log=log,
                                            verification=ac.VerificationRequest(description="done", backend=bound)))
    assert calls == [] and log.list_events() == []


@pytest.mark.parametrize("signal_type", [RuntimeError, AutoControlAssertionException, OperationCancelledError,
                                        CancelledError, asyncio.CancelledError, KeyboardInterrupt, SystemExit])
def test_verifier_failure_propagates_once_and_never_retries(located, signal_type):
    calls, log = located
    signal = signal_type("controlled failure")

    def verify():
        calls.append("verify")
        raise signal

    with pytest.raises(signal_type) as caught:
        ac.self_heal_run(ac.SelfHealRequest(template_path="fake.png", operation="click", log=log,
                                            verification=ac.VerificationRequest(verifier=verify)))
    assert caught.value is signal and calls == ["click", "verify"]
    events = log.list_events()
    if signal_type in (RuntimeError, AutoControlAssertionException):
        event, = events
        assert event.operation_status == "verification_error" and event.verified is None
        assert event.verification_error and event.operation_error is None
    else:
        assert not events


def test_audit_failure_preserves_original_verifier_exception(located, monkeypatch):
    _, log = located
    signal = RuntimeError("verification failed originally")

    def fail():
        raise signal

    monkeypatch.setattr(log, "append", lambda *_: (_ for _ in ()).throw(TypeError("audit failed")))
    with pytest.raises(RuntimeError) as caught:
        ac.self_heal_run(ac.SelfHealRequest(template_path="fake.png", operation="click", log=log,
                                            verification=ac.VerificationRequest(verifier=fail)))
    assert caught.value is signal


@pytest.mark.parametrize("value", [1, "yes", None])
def test_callback_rejects_truthy_or_unknown_values(located, value):
    _, log = located
    with pytest.raises(ac.SelfHealRequestError, match="return bool"):
        ac.self_heal_run(ac.SelfHealRequest(template_path="fake.png", operation="click", log=log,
                                            verification=ac.VerificationRequest(verifier=lambda: value)))
    event, = log.list_events()
    assert event.verified is None and event.operation_status == "verification_error"


def test_vlm_rejects_non_boolean_result(located, monkeypatch):
    _, log = located
    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical",
                        lambda *_a, **_k: (Image.new("RGB", (8, 8)), 100, 200))
    with pytest.raises(VLMRequestError, match="return bool"):
        ac.self_heal_run(ac.SelfHealRequest(template_path="fake.png", operation="click", log=log,
                                            verification=ac.VerificationRequest(description="done", backend=Verifier(1))))
    assert log.list_events()[0].verified is None


@pytest.mark.parametrize("failure", ["miss", "click"])
def test_verification_never_runs_without_successful_dispatch(located, monkeypatch, failure):
    calls, log = located

    def fail(*_a, **_k):
        raise RuntimeError("controlled error")

    target = ("je_auto_control.wrapper.auto_control_image.locate_image_center" if failure == "miss"
              else "je_auto_control.utils.self_healing.locator._click_at")
    monkeypatch.setattr(target, fail)
    request = ac.SelfHealRequest(template_path="fake.png", operation="click", log=log,
                                verification=ac.VerificationRequest(verifier=lambda: pytest.fail("must not verify")))
    if failure == "click":
        with pytest.raises(RuntimeError):
            ac.self_heal_run(request)
    else:
        assert not ac.self_heal_run(request).outcome.found
    assert calls == [] and log.list_events()[0].verified is None


@pytest.mark.parametrize("options", [{"detect_threshold": True}, {"detect_threshold": float("nan")},
                                    {"detect_threshold": 10**1000}, {"screen_region": [0, 0, True, 3]},
                                    {"screen_region": [0, 0, -1, 3]}, {"model": "bad\x00value"},
                                    {"operation": "wait"}, {"raise_on_miss": 1}, {"mouse_keycode": None}])
def test_invalid_options_are_rejected_before_execution(options):
    with pytest.raises(ac.SelfHealRequestError):
        ac.SelfHealRequest(description="submit", **options)


def test_request_copies_nested_regions():
    region = [0, 0, 4, 5]
    verification = ac.VerificationRequest(description="done", screen_region=region)
    request = ac.SelfHealRequest(description="submit", screen_region=region)
    region[2] = -1
    assert request.screen_region == verification.screen_region == (0, 0, 4, 5)
    with pytest.raises(FrozenInstanceError):
        request.operation = "click"


def test_verification_metadata_masks_current_secrets(located):
    from dataclasses import replace
    from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope
    calls, log = located
    ac.self_heal_run(ac.SelfHealRequest(template_path="fake.png", operation="click", log=log,
                                       verification=ac.VerificationRequest(verifier=lambda: True)))
    event, = log.list_events()
    log.clear()
    with secret_log_scope():
        remember_secret("private-value")
        log.append(replace(event, verification_description="private-value", verification_model="private-value",
                           verification_backend="private-value", verification_error="private-value"))
        saved, = log.list_events()
    assert calls == ["click"] and saved.verification_description == "***"
    assert saved.verification_model == saved.verification_backend == saved.verification_error == "***"
    assert "private-value" not in log.path.read_text(encoding="utf-8")
