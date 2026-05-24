"""Tests for the self-healing locator (image → VLM fallback)."""
from pathlib import Path

import pytest

from je_auto_control.utils.exception.exceptions import ImageNotFoundException
from je_auto_control.utils.self_healing import (
    HealEvent, HealEventLog, METHOD_IMAGE, METHOD_MISS, METHOD_VLM,
    SelfHealError, self_heal_click, self_heal_locate,
)
from je_auto_control.utils.self_healing import locator as locator_mod


@pytest.fixture
def temp_log(tmp_path: Path) -> HealEventLog:
    return HealEventLog(path=tmp_path / "events.jsonl")


def _patch_image_hit(monkeypatch, coords):
    def fake(template_path, detect_threshold):
        return coords, None
    monkeypatch.setattr(locator_mod, "_try_image", fake)


def _patch_image_miss(monkeypatch, reason="cant find"):
    def fake(template_path, detect_threshold):
        return None, reason
    monkeypatch.setattr(locator_mod, "_try_image", fake)


def _patch_vlm_hit(monkeypatch, coords):
    def fake(description, screen_region, model):
        return coords, None
    monkeypatch.setattr(locator_mod, "_try_vlm", fake)


def _patch_vlm_miss(monkeypatch, reason="vlm down"):
    def fake(description, screen_region, model):
        return None, reason
    monkeypatch.setattr(locator_mod, "_try_vlm", fake)


def test_locate_requires_template_or_description(temp_log):
    with pytest.raises(ValueError):
        self_heal_locate(log=temp_log)


def test_locate_returns_image_hit_without_calling_vlm(monkeypatch, temp_log):
    _patch_image_hit(monkeypatch, (40, 80))
    sentinel = {"called": False}

    def boom(*args, **kwargs):
        sentinel["called"] = True
        return None, "should not run"

    monkeypatch.setattr(locator_mod, "_try_vlm", boom)
    outcome = self_heal_locate(
        template_path="x.png", description="green button",
        log=temp_log,
    )
    assert outcome.found is True
    assert outcome.coordinates == (40, 80)
    assert outcome.method == METHOD_IMAGE
    assert sentinel["called"] is False


def test_locate_falls_back_to_vlm_on_image_miss(monkeypatch, temp_log):
    _patch_image_miss(monkeypatch)
    _patch_vlm_hit(monkeypatch, (200, 250))
    outcome = self_heal_locate(
        template_path="x.png", description="green button",
        log=temp_log,
    )
    assert outcome.method == METHOD_VLM
    assert outcome.coordinates == (200, 250)
    assert outcome.image_error == "cant find"


def test_locate_reports_miss_when_both_fail(monkeypatch, temp_log):
    _patch_image_miss(monkeypatch, "image-bad")
    _patch_vlm_miss(monkeypatch, "vlm-bad")
    outcome = self_heal_locate(
        template_path="x.png", description="x", log=temp_log,
    )
    assert outcome.found is False
    assert outcome.method == METHOD_MISS
    assert outcome.image_error == "image-bad"
    assert outcome.vlm_error == "vlm-bad"


def test_locate_raises_on_miss_when_requested(monkeypatch, temp_log):
    _patch_image_miss(monkeypatch)
    _patch_vlm_miss(monkeypatch)
    with pytest.raises(SelfHealError):
        self_heal_locate(
            template_path="x.png", description="y",
            log=temp_log, raise_on_miss=True,
        )


def test_locate_appends_log_event(monkeypatch, temp_log):
    _patch_image_hit(monkeypatch, (1, 2))
    self_heal_locate(template_path="x.png", log=temp_log)
    events = temp_log.list_events()
    assert len(events) == 1
    assert events[0].method == METHOD_IMAGE
    assert events[0].coordinates == [1, 2]


def test_log_clear_removes_file(monkeypatch, temp_log):
    _patch_image_hit(monkeypatch, (3, 4))
    self_heal_locate(template_path="x.png", log=temp_log)
    assert temp_log.path.exists()
    temp_log.clear()
    assert temp_log.list_events() == []
    assert not temp_log.path.exists()


def test_log_list_skips_malformed_lines(temp_log):
    temp_log.path.parent.mkdir(parents=True, exist_ok=True)
    with temp_log.path.open("w", encoding="utf-8") as fp:
        fp.write("not-json\n")
        fp.write("{\"method\": \"image\", \"timestamp\": \"now\", "
                 "\"coordinates\": [1, 2], \"duration_ms\": 0.5}\n")
    events = temp_log.list_events()
    assert len(events) == 1
    assert events[0].method == "image"
    assert events[0].coordinates == [1, 2]


def test_click_uses_resolved_coordinates(monkeypatch, temp_log):
    _patch_image_hit(monkeypatch, (50, 60))
    captured = {}

    def fake_click(coords, keycode):
        captured["coords"] = coords
        captured["keycode"] = keycode

    monkeypatch.setattr(locator_mod, "_click_at", fake_click)
    outcome = self_heal_click(
        template_path="x.png", log=temp_log, mouse_keycode="mouse_right",
    )
    assert outcome.found is True
    assert captured == {"coords": (50, 60), "keycode": "mouse_right"}


def test_click_does_not_invoke_mouse_on_miss(monkeypatch, temp_log):
    _patch_image_miss(monkeypatch)
    _patch_vlm_miss(monkeypatch)
    captured = {"called": False}

    def fake_click(coords, keycode):
        captured["called"] = True

    monkeypatch.setattr(locator_mod, "_click_at", fake_click)
    outcome = self_heal_click(
        template_path="x.png", description="x", log=temp_log,
    )
    assert outcome.found is False
    assert captured["called"] is False


def test_try_image_translates_image_not_found(monkeypatch):
    def boom(_path, **_kwargs):
        raise ImageNotFoundException("nope")

    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_image.locate_image_center",
        boom,
    )
    coords, error = locator_mod._try_image("x.png", 0.9)
    assert coords is None
    assert "nope" in (error or "")


def test_outcome_to_dict_normalises_tuple():
    outcome = locator_mod.HealOutcome(
        found=True, coordinates=(7, 9), method=METHOD_VLM,
    )
    data = outcome.to_dict()
    assert data["coordinates"] == [7, 9]
    assert data["method"] == METHOD_VLM


def test_heal_event_to_dict_roundtrips():
    event = HealEvent(
        timestamp="t", method=METHOD_IMAGE,
        coordinates=[1, 2], duration_ms=1.0,
        template_path="x.png", description=None,
        image_error=None, vlm_error=None,
    )
    assert HealEvent(**event.to_dict()) == event


def test_executor_registers_self_heal_commands():
    from je_auto_control.utils.executor.action_executor import executor
    commands = executor.known_commands()
    assert {
        "AC_self_heal_locate", "AC_self_heal_click",
        "AC_self_heal_log_list", "AC_self_heal_log_clear",
    } <= commands


def test_facade_exports_self_heal_api():
    import je_auto_control as ac
    assert hasattr(ac, "self_heal_locate")
    assert hasattr(ac, "self_heal_click")
    assert hasattr(ac, "HealOutcome")
    assert hasattr(ac, "default_heal_log")


def test_mcp_factory_registers_self_heal_tools():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert {
        "ac_self_heal_locate", "ac_self_heal_click",
        "ac_self_heal_log_list", "ac_self_heal_log_clear",
    } <= names


def test_package_facade_stays_qt_free():
    """Import the facade in a fresh interpreter so the check isn't polluted
    by GUI tests that may have already imported PySide6 in this session."""
    import subprocess
    import sys
    script = (
        "import sys, je_auto_control  # noqa: F401\n"
        "qt = [m for m in sys.modules if 'PySide6' in m]\n"
        "import json; print(json.dumps(qt))\n"
    )
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
    # reason: subprocess spawned with [sys.executable, ...] — known
    # interpreter, fixed argv list, no shell=True, no user input.
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, check=True, timeout=60,
    )
    qt_modules = result.stdout.strip()
    assert qt_modules in ("[]", ""), (
        f"je_auto_control facade pulled PySide6 into sys.modules: {qt_modules}"
    )
