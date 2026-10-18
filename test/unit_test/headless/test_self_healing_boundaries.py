"""Self-healing must preserve interruption and mask persisted diagnostics."""
import asyncio
from concurrent.futures import CancelledError as FutureCancelledError
from dataclasses import replace

import pytest

from je_auto_control.utils.exception.exceptions import ImageNotFoundException
from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope
from je_auto_control.utils.mcp_server.context import OperationCancelledError
from je_auto_control.utils.self_healing import HealEvent, HealEventLog, self_heal_click, self_heal_locate


@pytest.mark.parametrize("entry", [self_heal_locate, self_heal_click])
@pytest.mark.parametrize("strategy", ["image", "vlm"])
@pytest.mark.parametrize("signal_type", [
    OperationCancelledError, FutureCancelledError, asyncio.CancelledError, KeyboardInterrupt, SystemExit,
])
def test_interruption_never_falls_back_clicks_or_logs(monkeypatch, tmp_path, entry, strategy, signal_type):
    signal = signal_type("cancelled-probe")
    calls = []
    log = HealEventLog(tmp_path / "events.jsonl")

    def image(*_args, **_kwargs):
        calls.append("image")
        if strategy == "image":
            raise signal
        raise ImageNotFoundException("missing")

    def vlm(*_args, **_kwargs):
        calls.append("vlm")
        if strategy == "vlm":
            raise signal
        return (4, 5)

    monkeypatch.setattr("je_auto_control.wrapper.auto_control_image.locate_image_center", image)
    monkeypatch.setattr("je_auto_control.utils.vision.vlm_api.locate_by_description", vlm)
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", lambda *_: calls.append("click"))
    with pytest.raises(signal_type) as caught:
        entry(template_path="probe.png", description="probe", log=log)
    assert caught.value is signal
    assert calls == (["image"] if strategy == "image" else ["image", "vlm"])
    assert not log.path.exists()


@pytest.mark.parametrize("field", ["timestamp", "method", "template_path", "description", "image_error", "vlm_error"])
def test_log_masks_known_values_before_write_without_mutating_event(tmp_path, field):
    secret = '密碼-"probe"\nvalue'
    event = replace(HealEvent("now", "image", [4, 5], 1.0), **{field: f"before:{secret}:after"})
    log = HealEventLog(tmp_path / "events.jsonl")
    with secret_log_scope():
        remember_secret(secret)
        log.append(event)
    assert getattr(log.list_events()[0], field) == "before:***:after"
    assert getattr(event, field) == f"before:{secret}:after"
    assert "probe" not in log.path.read_text(encoding="utf-8")


def test_read_masks_legacy_record_in_current_scope_without_rewriting_file(tmp_path):
    log = HealEventLog(tmp_path / "events.jsonl")
    event = HealEvent("now", "vlm", [4, 5], 1.0, description="legacy-secret")
    log.append(event)
    original = log.path.read_bytes()
    with secret_log_scope():
        remember_secret("legacy-secret")
        assert log.list_events()[0].description == "***"
    assert log.path.read_bytes() == original
    assert log.list_events()[0] == event


@pytest.mark.parametrize("surface", ["command", "mcp"])
@pytest.mark.parametrize("operation", ["locate", "click"])
def test_registered_surfaces_preserve_cancellation(monkeypatch, tmp_path, surface, operation):
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry

    signal = OperationCancelledError("boundary-probe")
    log = HealEventLog(tmp_path / "events.jsonl")
    calls = []

    def cancel(*_args, **_kwargs):
        raise signal

    monkeypatch.setattr("je_auto_control.wrapper.auto_control_image.locate_image_center", cancel)
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator.default_heal_log", log)
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._try_vlm", lambda *_: calls.append("vlm"))
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", lambda *_: calls.append("click"))
    arguments = {"template_path": "probe.png", "description": "probe"}
    with pytest.raises(OperationCancelledError) as caught:
        if surface == "command":
            executor.execute_action([[f"AC_self_heal_{operation}", arguments]])
        else:
            tool = next(tool for tool in build_default_tool_registry() if tool.name == f"ac_self_heal_{operation}")
            tool.handler(**arguments)
    assert caught.value is signal
    assert calls == []
    assert not log.path.exists()


def test_cancellation_is_not_formatted(monkeypatch, tmp_path):
    class UnformattableCancellation(OperationCancelledError):
        def __repr__(self):
            pytest.fail("cancellation must propagate before repr")

    signal = UnformattableCancellation("probe")

    def cancel(*_args, **_kwargs):
        raise signal

    monkeypatch.setattr("je_auto_control.wrapper.auto_control_image.locate_image_center", cancel)
    with pytest.raises(OperationCancelledError) as caught:
        self_heal_locate(template_path="probe.png", log=HealEventLog(tmp_path / "events.jsonl"))
    assert caught.value is signal


def test_successful_fallback_keeps_original_outcome_and_masks_only_audit(monkeypatch, tmp_path):
    secret = "private-locator-value"
    log = HealEventLog(tmp_path / "events.jsonl")

    def image(*_args, **_kwargs):
        raise RuntimeError(f"ordinary miss: {secret}")

    monkeypatch.setattr("je_auto_control.wrapper.auto_control_image.locate_image_center", image)
    monkeypatch.setattr("je_auto_control.utils.vision.vlm_api.locate_by_description", lambda *_a, **_k: (4, 5))
    with secret_log_scope():
        remember_secret(secret)
        outcome = self_heal_locate(template_path=secret, description=secret, log=log)
    assert outcome.found and outcome.coordinates == (4, 5)
    assert outcome.template_path == outcome.description == secret
    assert secret in outcome.image_error
    stored = log.list_events()[0]
    assert stored.template_path == stored.description == "***"
    assert "ordinary miss" in stored.image_error
    assert secret not in log.path.read_text(encoding="utf-8")
