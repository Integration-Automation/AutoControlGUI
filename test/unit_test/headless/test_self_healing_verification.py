"""Declarative post-click checks: a JSON step can fill ``action_verified``.

The locators, the click and the screen probes are all replaced by fakes; no
mouse moves and no screen is read.
"""
import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlScreenException, ImageNotFoundException,
)
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.self_healing import (
    HealEventLog, HealVerificationError, build_verifier, self_heal_click,
)
from je_auto_control.utils.self_healing import locator as locator_mod
from je_auto_control.utils.self_healing import verification


@pytest.fixture()
def temp_log(tmp_path):
    return HealEventLog(tmp_path / "heal.jsonl")


@pytest.fixture()
def screen(monkeypatch):
    """A fake screen: which templates and texts are on it, and what was clicked."""
    state = {"images": {"submit.png"}, "texts": set(), "clicks": [], "probes": []}

    def fake_image(template_path, detect_threshold, region):
        state["probes"].append(("image", template_path, detect_threshold, region))
        return template_path in state["images"]

    def fake_text(text, region, lang="eng", min_confidence=60.0, case_sensitive=False):
        state["probes"].append(("text", text, region, lang))
        return text in state["texts"]

    def fake_click(coordinates, keycode):
        state["clicks"].append((coordinates, keycode))
        # Clicking Submit closes it and shows the confirmation.
        state["images"].discard("submit.png")
        state["images"].add("dialog.png")
        state["texts"].add("Saved")

    monkeypatch.setattr(verification, "image_on_screen", fake_image)
    monkeypatch.setattr(verification, "text_on_screen", fake_text)
    monkeypatch.setattr(locator_mod, "_click_at", fake_click)
    monkeypatch.setattr(locator_mod, "_try_image",
                        lambda template, threshold, frame=None: ((10, 20), None))
    monkeypatch.setattr(locator_mod, "_try_image_in_region",
                        lambda template, threshold, region: ((10, 20), None))
    return state


@pytest.mark.parametrize("spec, verified", [
    ({"type": "image_gone"}, True),
    ({"type": "image_present", "template_path": "dialog.png"}, True),
    ({"type": "text_present", "text": "Saved"}, True),
    ({"type": "image_present"}, False),                 # the clicked template is gone
    ({"type": "image_gone", "template_path": "dialog.png"}, False),
    ({"type": "text_present", "text": "Failed"}, False),
])
def test_a_declarative_check_fills_action_verified(screen, temp_log, spec, verified):
    outcome = self_heal_click(template_path="submit.png", log=temp_log,
                              verify={**spec, "timeout_s": 0})
    assert outcome.found is True and outcome.action == "click"
    assert outcome.action_verified is verified
    assert screen["clicks"] == [((10, 20), "mouse_left")]
    assert temp_log.list_events()[0].action_verified is verified


def test_without_a_check_it_is_still_none(screen, temp_log):
    assert self_heal_click(template_path="submit.png", log=temp_log).action_verified is None


def test_the_json_command_carries_the_check(screen, temp_log, monkeypatch):
    monkeypatch.setattr(locator_mod, "default_heal_log", temp_log)
    record = Executor().execute_action([["AC_self_heal_click", {
        "template_path": "submit.png",
        "verify": {"type": "image_gone", "timeout_s": 0}}]], raise_on_error=True)
    result = next(iter(record.values()))
    assert result["action_verified"] is True and result["action"] == "click"


def test_the_mcp_handler_carries_the_check(screen, temp_log, monkeypatch):
    from je_auto_control.utils.mcp_server.tools import (
        _handlers_locators, build_default_tool_registry,
    )
    monkeypatch.setattr(locator_mod, "default_heal_log", temp_log)
    result = _handlers_locators.self_heal_click(
        template_path="submit.png", verify={"type": "text_present", "text": "Saved",
                                            "timeout_s": 0})
    assert result["action_verified"] is True
    tool = {tool.name: tool for tool in build_default_tool_registry()}["ac_self_heal_click"]
    assert "verify" in tool.input_schema["properties"]


def test_the_click_region_and_template_are_what_the_check_uses(screen, temp_log):
    self_heal_click(template_path="submit.png", screen_region=[0, 0, 400, 300],
                    detect_threshold=0.8, log=temp_log,
                    verify={"type": "image_gone", "detect_threshold": 0.95, "timeout_s": 0})
    assert screen["probes"] == [("image", "submit.png", 0.95, (0, 0, 400, 300))]
    screen["probes"].clear()
    screen["images"].add("submit.png")
    self_heal_click(template_path="submit.png", screen_region=[0, 0, 400, 300], log=temp_log,
                    verify={"type": "text_present", "text": "Saved", "lang": "chi_tra",
                            "screen_region": [5, 5, 50, 50], "timeout_s": 0})
    assert screen["probes"] == [("text", "Saved", (5, 5, 50, 50), "chi_tra")]


def test_a_malformed_check_is_refused_before_anything_is_clicked(screen, temp_log):
    for spec, message in [
        ({"type": "pixel"}, "unknown verify type"),
        ({}, "unknown verify type"),
        ({"type": "image_gone", "text": "x"}, "unknown verify option"),
        ({"type": "text_present"}, "non-empty text"),
        ({"type": "image_gone", "timeout_s": -1}, "timeout_s must be between"),
        ({"type": "image_gone", "timeout_s": "soon"}, "timeout_s must be a number"),
        ({"type": "image_gone", "screen_region": [5, 5, 1, 1]}, "x2 > x1"),
        ({"type": "image_gone", "detect_threshold": 7}, "detect_threshold must be between"),
    ]:
        with pytest.raises(HealVerificationError, match=message):
            self_heal_click(template_path="submit.png", log=temp_log, verify=spec)
    assert screen["clicks"] == [] and temp_log.list_events() == []


def test_an_image_check_needs_a_template_when_the_click_had_none(screen, monkeypatch):
    monkeypatch.setattr(locator_mod, "_try_vlm", lambda *args: ((1, 2), None))
    with pytest.raises(HealVerificationError, match="needs template_path"):
        self_heal_click(description="the button", verify={"type": "image_gone"})
    assert screen["clicks"] == []


def test_a_check_that_cannot_run_raises_and_is_logged_unverified(screen, temp_log, monkeypatch):
    def broken(*_args):
        raise AutoControlScreenException("capture failed")

    monkeypatch.setattr(verification, "image_on_screen", broken)
    with pytest.raises(HealVerificationError, match="could not be carried out"):
        self_heal_click(template_path="submit.png", log=temp_log,
                        verify={"type": "image_gone", "timeout_s": 0})
    event = temp_log.list_events()[0]
    assert (event.action, event.action_verified) == ("click", None)
    assert len(screen["clicks"]) == 1


def test_the_check_is_polled_until_it_holds_or_time_runs_out():
    now = [0.0]
    slept = []
    answers = iter([False, False, True])

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    verify = build_verifier({"type": "text_present", "text": "x", "timeout_s": 5, "poll_s": 1},
                            clock=lambda: now[0], sleep=sleep)
    original = verification.text_on_screen
    verification.text_on_screen = lambda *args, **kwargs: next(answers)
    try:
        assert verify(None) is True and slept == [1.0, 1.0]
        verification.text_on_screen = lambda *args, **kwargs: False
        slept.clear()
        assert verify(None) is False
        assert len(slept) == 5 and now[0] >= 7.0
    finally:
        verification.text_on_screen = original


def test_image_on_screen_tells_absent_from_unreadable(monkeypatch):
    from je_auto_control.utils.cv2_utils import template_detection
    calls = []

    def fake_find(image, threshold, screen_region=None):
        calls.append((image, threshold, screen_region))
        if image == "absent.png":
            raise ImageNotFoundException("not found")
        if image == "broken.png":
            raise OSError("cannot read")
        return [True, [1, 2, 3, 4]]

    monkeypatch.setattr(template_detection, "find_image", fake_find)
    assert verification.image_on_screen("there.png", 0.9, (10, 20, 110, 70)) is True
    assert calls[-1] == ("there.png", 0.9, (10, 20, 100, 50))    # corners -> x, y, w, h
    assert verification.image_on_screen("absent.png", 0.9, None) is False
    with pytest.raises(OSError):
        verification.image_on_screen("broken.png", 0.9, None)


def test_the_tab_passes_the_typed_check(screen, temp_log, monkeypatch):
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from je_auto_control.gui import self_healing_tab
    monkeypatch.setattr(locator_mod, "default_heal_log", temp_log)
    monkeypatch.setattr(self_healing_tab, "default_heal_log", temp_log)
    tab = self_healing_tab.SelfHealingTab()
    try:
        tab._template_input.setText("submit.png")
        tab._verify_input.setText('{"type": "image_gone", "timeout_s": 0}')
        tab._on_click()
        assert temp_log.list_events()[0].action_verified is True
        tab._verify_input.setText("[1, 2]")
        tab._on_click()
        assert self_healing_tab._t("self_heal_verify_invalid") in tab._status.text()
        assert len(screen["clicks"]) == 1
    finally:
        tab.deleteLater()
        app.processEvents()
