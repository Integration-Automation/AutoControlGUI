"""Live self-healing shares one controlled capture and reports truthful operation evidence."""
import io
from hashlib import sha256
from pathlib import Path

import pytest
from PIL import Image

from je_auto_control.utils.exception.exceptions import AutoControlScreenException
from je_auto_control.utils.self_healing import HealEventLog, self_heal_click, self_heal_locate
from je_auto_control.utils.vision.backends.base import VLMBackend

FIXTURES = Path(__file__).resolve().parents[3] / "benchmarks/self_healing/fixtures"


@pytest.fixture(autouse=True)
def no_native_capture(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("runtime tests must use injected frames, never the desktop")

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame._load_image_grab", forbidden)
    monkeypatch.setattr("je_auto_control.utils.vision.vlm_api._capture_screenshot_bytes", forbidden)


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def grab(region=None, *, all_screens=True, **_kwargs):
        calls.append((region, all_screens))
        with Image.open(FIXTURES / "frame_new.png") as original:
            if region is None:
                return original.copy(), -80, -40
            left, top, width, height = region
            box = (left + 80, top + 40, left + 80 + width, top + 40 + height)
            return original.crop(box), left, top

    monkeypatch.setattr("je_auto_control.utils.cv2_utils.template_detection.grab_logical", grab)
    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical", grab)
    return calls


def backend(monkeypatch, point=(6, 5)):
    images = []

    class Backend(VLMBackend):
        available, name = True, "controlled"

        def locate(self, image_bytes, description, model=None, image_mime="image/png"):
            images.append((image_bytes, model))
            return point

    monkeypatch.setattr("je_auto_control.utils.vision.vlm_api.get_backend", lambda: Backend())
    return images


def test_image_region_is_applied_before_matching(captured, tmp_path):
    log = HealEventLog(tmp_path / "events.jsonl")
    outcome = self_heal_locate(str(FIXTURES / "new.png"), screen_region=[-64, -28, -40, 0], log=log)
    assert captured == [((-64, -28, 24, 28), True)]
    assert outcome.coordinates == (-52, -18)
    event = log.list_events()[0]
    assert event.schema_version == 2 and event.origin == [-64, -28]
    assert event.frame_hash and event.locator_version
    assert event.verified is None


def test_fallback_reuses_capture_and_origin(captured, monkeypatch, tmp_path):
    images = backend(monkeypatch)
    log = HealEventLog(tmp_path / "events.jsonl")
    outcome = self_heal_locate(str(FIXTURES / "old.png"), "submit", screen_region=[-72, -34, -60, -24],
                               model="controlled-model", log=log)
    assert captured == [((-72, -34, 12, 10), True)]
    assert outcome.coordinates == (-66, -29) and outcome.method == "vlm"
    with Image.open(io.BytesIO(images[0][0])) as image:
        assert image.size == (12, 10)
    event = log.list_events()[0]
    assert event.backend == "controlled" and event.model == "controlled-model"
    assert set(event.strategy_times_ms) == {"image", "vlm"}
    assert event.run_id and event.step_id and event.locator_id
    assert event.verified is None and event.operation_status == "not_requested"
    assert event.frame_hash == sha256(images[0][0]).hexdigest()


def test_capture_failure_is_not_retried_for_fallback(monkeypatch, tmp_path):
    calls = []

    def fail(*_args, **_kwargs):
        calls.append("capture")
        raise AutoControlScreenException("controlled capture failure")

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical", fail)
    monkeypatch.setattr("je_auto_control.utils.cv2_utils.template_detection.grab_logical", fail)
    monkeypatch.setattr("je_auto_control.utils.cv2_utils.region_capture.grab_screen_region", fail)
    images = backend(monkeypatch)
    outcome = self_heal_locate(str(FIXTURES / "old.png"), "submit", log=HealEventLog(tmp_path / "events.jsonl"))
    assert calls == ["capture"] and images == []
    assert not outcome.found


def test_click_failure_is_recorded_once_without_claiming_verification(captured, monkeypatch, tmp_path):
    signal = RuntimeError("controlled click failure")

    def fail(*_args):
        raise signal

    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", fail)
    log = HealEventLog(tmp_path / "events.jsonl")
    with pytest.raises(RuntimeError) as caught:
        self_heal_click(str(FIXTURES / "new.png"), log=log)
    assert caught.value is signal
    assert len(captured) == 1
    event, = log.list_events()
    assert event.operation == "click" and event.operation_status == "error"
    assert event.verified is None and "controlled click failure" in event.operation_error


def test_primary_request_preserves_self_capturing_backend_origin(monkeypatch):
    from je_auto_control.utils.monitor_layout.logical_frame import grab_logical

    class Grabber:
        @staticmethod
        def grab():
            return Image.new("RGB", (64, 48))

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame._backend_frame_origin", lambda: (-80, -40))
    image, x, y = grab_logical(all_screens=False, grabber=Grabber())
    try:
        assert (x, y) == (-80, -40)
    finally:
        image.close()


def test_vlm_only_keeps_primary_request_and_real_origin(captured, monkeypatch, tmp_path):
    backend(monkeypatch)
    log = HealEventLog(tmp_path / "events.jsonl")
    outcome = self_heal_locate(description="submit", log=log)
    assert captured == [(None, False)]
    assert outcome.coordinates == (-74, -35)
    assert set(log.list_events()[0].strategy_times_ms) == {"vlm"}


def test_clipped_capture_origin_is_used_instead_of_requested_corner(monkeypatch, tmp_path):
    calls = []

    def grab(region, **_kwargs):
        calls.append(region)
        return Image.new("RGB", (10, 10)), -80, -40

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical", grab)
    backend(monkeypatch, (0, 0))
    log = HealEventLog(tmp_path / "events.jsonl")
    outcome = self_heal_locate(str(FIXTURES / "old.png"), "submit", screen_region=[-100, -60, -70, -30], log=log)
    assert outcome.coordinates == (-80, -40) and calls == [(-100, -60, 30, 30)]
    event, = log.list_events()
    assert event.origin == [-80, -40] and event.frame_size == [10, 10]
    assert event.screen_region == [-100, -60, -70, -30]


def test_unavailable_backend_does_not_capture(captured, monkeypatch, tmp_path):
    instance = VLMBackend()
    monkeypatch.setattr("je_auto_control.utils.vision.vlm_api.get_backend", lambda: instance)
    log = HealEventLog(tmp_path / "events.jsonl")
    assert not self_heal_locate(description="submit", log=log).found
    assert captured == []
    event, = log.list_events()
    assert event.frame_hash is event.capture_ms is event.locator_version is None


def test_outside_reply_is_a_miss_not_a_click(captured, monkeypatch, tmp_path):
    backend(monkeypatch, (1000, 1000))
    clicks = []
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", lambda *_: clicks.append(True))
    log = HealEventLog(tmp_path / "events.jsonl")
    assert not self_heal_click(description="submit", log=log).found
    assert len(captured) == 1 and clicks == []
    event, = log.list_events()
    assert event.operation_status == "not_found" and event.verified is None


@pytest.mark.parametrize("where", ["capture", "click"])
def test_cancelled_capture_or_click_preserves_signal_and_creates_no_event(captured, monkeypatch, tmp_path, where):
    from je_auto_control.utils.mcp_server.context import OperationCancelledError

    signal = OperationCancelledError("controlled")

    def cancel(*_args, **_kwargs):
        raise signal

    if where == "capture":
        monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical", cancel)
    else:
        monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", cancel)
    log = HealEventLog(tmp_path / "events.jsonl")
    with pytest.raises(OperationCancelledError) as caught:
        self_heal_click(str(FIXTURES / "new.png"), log=log)
    assert caught.value is signal and not log.path.exists()


def test_click_and_audit_failure_preserves_original(captured, monkeypatch, tmp_path):
    signal = RuntimeError("original click failure")

    def fail(*_args, **_kwargs):
        raise signal

    def unavailable(*_args):
        raise RuntimeError("secondary audit failure")

    log = HealEventLog(tmp_path / "events.jsonl")
    monkeypatch.setattr(log, "append", unavailable)
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", fail)
    with pytest.raises(RuntimeError) as caught:
        self_heal_click(str(FIXTURES / "new.png"), log=log)
    assert caught.value is signal


def test_content_versions_change_without_changing_locator_id(captured, tmp_path):
    template = tmp_path / "template.png"
    template.write_bytes((FIXTURES / "new.png").read_bytes())
    log = HealEventLog(tmp_path / "events.jsonl")
    assert self_heal_locate(str(template), log=log).found
    template.write_bytes((FIXTURES / "old.png").read_bytes())
    assert not self_heal_locate(str(template), log=log).found
    first, second = log.list_events()
    assert first.locator_id == second.locator_id
    assert first.locator_version != second.locator_version
    assert first.frame_hash == second.frame_hash


def test_configured_template_version_does_not_change_when_fallback_runs(monkeypatch, tmp_path):
    frames = iter(["frame_new.png", "frame_old.png"])

    def grab(*_args, **_kwargs):
        with Image.open(FIXTURES / next(frames)) as image:
            return image.copy(), -80, -40

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical", grab)
    backend(monkeypatch)
    log = HealEventLog(tmp_path / "events.jsonl")
    arguments = {"template_path": str(FIXTURES / "new.png"), "description": "submit", "model": "controlled", "log": log}
    assert self_heal_locate(**arguments).method == "image"
    assert self_heal_locate(**arguments).method == "vlm"
    first, second = log.list_events()
    assert first.locator_version == second.locator_version
    assert first.frame_hash != second.frame_hash


def test_journal_command_identity_and_mcp_share_telemetry(captured, monkeypatch, tmp_path):
    from je_auto_control.utils.action_journal import ActionJournal, journal_scope, read_events
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry

    log = HealEventLog(tmp_path / "events.jsonl")
    journal = tmp_path / "journal.jsonl"
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator.default_heal_log", log)
    arguments = {"template_path": str(FIXTURES / "new.png"), "screen_region": [-64, -28, -40, 0]}
    with journal_scope(ActionJournal(journal), run_id="source-run"):
        executor.execute_action([["AC_self_heal_locate", arguments]], raise_on_error=True)
    tool = next(tool for tool in build_default_tool_registry() if tool.name == "ac_self_heal_locate")
    assert tool.handler(**arguments)["coordinates"] == [-52, -18]
    command, remote = log.list_events()
    assert command.run_id == "source-run" and command.step_id == read_events(journal)[0].step_id
    assert remote.run_id != command.run_id and remote.frame_hash == command.frame_hash


def test_nested_scopes_restore_owner_and_release_frames(captured):
    from je_auto_control.utils.cv2_utils.locator_frame import current_locator_frame, locator_frame_scope

    with locator_frame_scope(None, all_screens=True) as outer:
        frame = outer.snapshot()
        assert "PNG" not in repr(frame)
        with locator_frame_scope(None, all_screens=False) as inner:
            assert inner.snapshot() is not frame
            assert current_locator_frame() is inner
        assert current_locator_frame() is outer and outer.snapshot() is frame
        assert inner.captured is None
    assert current_locator_frame() is None and outer.captured is None
    with pytest.raises(AutoControlScreenException, match="closed"):
        outer.snapshot()
    assert len(captured) == 2


def test_old_records_and_analytics_do_not_invent_operation_success(tmp_path):
    import json
    from je_auto_control.utils.heal_analytics import heal_stats

    log = HealEventLog(tmp_path / "events.jsonl")
    log.path.write_text(json.dumps({"timestamp": "old", "method": "vlm", "coordinates": [1, 2],
                                    "duration_ms": 1.0}) + "\n", encoding="utf-8")
    event, = log.list_events()
    assert event.schema_version == 1 and event.verified is None
    stats = heal_stats([event])
    assert stats["healed"] == stats["located"] == 1
    assert stats["verified_operations"] == 0
    assert stats["operation_success_rate"]["value"] is None


def test_successful_click_is_only_issued_not_verified(captured, monkeypatch, tmp_path):
    from je_auto_control.utils.heal_analytics import heal_stats

    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", lambda *_args: None)
    log = HealEventLog(tmp_path / "events.jsonl")
    assert self_heal_click(str(FIXTURES / "new.png"), log=log).found
    event, = log.list_events()
    assert event.operation_status == "issued" and event.verified is None
    assert set(event.strategy_times_ms) == {"image", "click"}
    stats = heal_stats([event])
    assert stats["located"] == 1 and stats["verified_operations"] == 0
    assert stats["verification_unknown"] == 1 and stats["operation_success_rate"]["denominator"] == 0


def test_explicit_operation_verification_has_its_own_population():
    from je_auto_control.utils.heal_analytics import heal_stats

    stats = heal_stats([
        {"coordinates": [1, 2], "operation": "click", "verified": True, "operation_status": "verified"},
        {"coordinates": [1, 2], "operation": "click", "verified": False, "operation_status": "issued"},
        {"coordinates": [1, 2], "operation": "click", "verified": None, "operation_status": "issued"},
        {"coordinates": [1, 2], "operation": "click", "verified": True, "operation_status": "error"},
    ])
    assert stats["verified_operations"] == 1 and stats["verification_unknown"] == 1
    assert stats["operation_success_rate"]["numerator"] == 1
    assert stats["operation_success_rate"]["denominator"] == 3


def test_resolved_provider_model_matches_reported_model(captured, monkeypatch, tmp_path):
    seen = []

    class Backend(VLMBackend):
        available, name = True, "controlled"

        def resolve_model(self, model=None):
            return model or "resolved-controlled-model"

        def locate(self, image_bytes, description, model=None, image_mime="image/png"):
            seen.append(model)
            return 1, 2

    monkeypatch.setattr("je_auto_control.utils.vision.vlm_api.get_backend", lambda: Backend())
    log = HealEventLog(tmp_path / "events.jsonl")
    assert self_heal_locate(description="submit", log=log).found
    event, = log.list_events()
    assert event.model == seen[0] == "resolved-controlled-model"
    assert event.locator_version is not None


def test_fixed_frame_vlm_reports_the_same_resolved_model():
    from je_auto_control.utils.self_healing import EvaluationSample, VLMFrameLocator

    seen = []

    class Backend(VLMBackend):
        available, name = True, "controlled"

        def resolve_model(self, model=None):
            return model or "resolved-controlled-model"

        def locate(self, image_bytes, description, model=None, image_mime="image/png"):
            seen.append(model)
            return 1, 2

    sample = EvaluationSample("provided", (FIXTURES / "frame_new.png").read_bytes())
    result = VLMFrameLocator(Backend(), "submit").locate(sample)
    assert result.model == seen[0] == "resolved-controlled-model"


@pytest.mark.parametrize("backend_name", ["anthropic", "openai"])
def test_provider_model_resolution_does_not_need_sdk_or_network(monkeypatch, backend_name):
    from je_auto_control.utils.vision.backends.anthropic_backend import AnthropicVLMBackend
    from je_auto_control.utils.vision.backends.openai_backend import OpenAIVLMBackend

    cls = {"anthropic": AnthropicVLMBackend, "openai": OpenAIVLMBackend}[backend_name]
    instance = object.__new__(cls)
    monkeypatch.setenv("AUTOCONTROL_VLM_MODEL", "controlled-model")
    assert instance.resolve_model() == "controlled-model"
    assert instance.resolve_model("explicit-model") == "explicit-model"


def test_new_metadata_is_masked_before_persistence(captured, monkeypatch, tmp_path):
    from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope

    backend(monkeypatch)
    secret = "controlled-private-model"
    log = HealEventLog(tmp_path / "events.jsonl")
    with secret_log_scope():
        remember_secret(secret)
        assert self_heal_locate(description="submit", model=secret, log=log).found
    assert log.list_events()[0].model == "***"
    assert secret not in log.path.read_text(encoding="utf-8")


def test_broken_failure_repr_does_not_prevent_ordinary_fallback(monkeypatch, tmp_path):
    class Broken(RuntimeError):
        def __repr__(self):
            raise ValueError("cannot format")

    def fail(*_args, **_kwargs):
        raise Broken()

    monkeypatch.setattr("je_auto_control.wrapper.auto_control_image.locate_image_center", fail)
    monkeypatch.setattr("je_auto_control.utils.vision.vlm_api.locate_by_description", lambda *_a, **_k: (1, 2))
    outcome = self_heal_locate("unused.png", "submit", log=HealEventLog(tmp_path / "events.jsonl"))
    assert outcome.found and "Broken" in outcome.image_error


def test_concurrent_attempts_have_independent_owners(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(2)
    owners = []
    from je_auto_control.utils.cv2_utils.locator_frame import current_locator_frame

    def grab(*_args, **_kwargs):
        owners.append(current_locator_frame())
        barrier.wait(timeout=3)
        with Image.open(FIXTURES / "frame_new.png") as image:
            return image.copy(), -80, -40

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical", grab)
    log = HealEventLog(tmp_path / "events.jsonl")
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(self_heal_locate, str(FIXTURES / "new.png"), log=log) for _ in range(2)]
        assert all(job.result(timeout=5).found for job in jobs)
    assert len(owners) == 2 and owners[0] is not owners[1]
    assert all(owner.captured is None for owner in owners)
    assert len({event.step_id for event in log.list_events()}) == 2
