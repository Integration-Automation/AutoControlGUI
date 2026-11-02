"""Completion uses source coverage and reviewed labels without native UI or browser access."""
from contextlib import closing
from types import SimpleNamespace

import pytest

from je_auto_control.utils.accessibility.element import AccessibilityElement
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskSpec
from je_auto_control.utils.agent_runtime.browser_target import BrowserTarget
from je_auto_control.utils.agent_runtime.file_target import FileTarget
from je_auto_control.utils.agent_runtime.policy import TaskPolicy
from je_auto_control.utils.agent_runtime.targets import DesktopTarget
from je_auto_control.utils.agent_runtime.verification import verify


def status(observation, condition):
    task = AgentTaskSpec.from_dict({"goal": "verify reviewed labels", "allowed_tools": ["AC_write"],
        "success_criteria": [{"kind": "screen", "spec": condition}]})
    return verify(TaskPolicy(task), [], observation)[0]["status"]


@pytest.mark.parametrize("condition,expected", [
    ({"text_present": "Saved"}, "passed"),
    ({"text_absent": "Missing"}, "unknown"),
    ({"text_absent": "Saved"}, "failed"),
    ({"text_present": "Saved", "text_absent": "Missing"}, "unknown"),
    ({"text_present": "Missing", "text_absent": "Saved"}, "failed"),
    ({"text_present": "Saved", "count": {"min": 1}}, "unknown"),
    ({"text_absent": "Saved", "count": {"equals": 0}}, "failed"),
])
def test_partial_clauses_combine_only_known_evidence(condition, expected):
    observation = {"elements": [{"name": "Saved"}], "semantic_observation": True, "text_redacted": True}
    assert status(observation, condition) == expected


@pytest.mark.parametrize("marker", [
    {"is_password": True}, {"sensitive": True}, {"text_redacted": True},
    {"is_password": None}, {"sensitive": 1}, {"text_redacted": "false"},
    {"visible": False}, {"visible": None}, {"visible": 1},
])
def test_masked_hidden_or_untyped_labels_cannot_supply_a_match(marker):
    observation = {"elements": [{"name": "[redacted]", "text": "SECRET", "value": "SECRET", **marker}],
                   "semantic_observation": True, "text_redacted": True}
    for text in ("[redacted]", "SECRET"):
        assert status(observation, {"text_present": text}) == "unknown"
        assert status(observation, {"text_absent": text}) == "unknown"


@pytest.mark.parametrize("field", ["name", "text", "value"])
def test_reviewed_text_shapes_keep_known_matches_without_stringifying_objects(field):
    observation = {"elements": [{field: {"Saved": True}}], "text_redacted": True}
    assert status(observation, {"text_present": "Saved"}) == "unknown"
    observation["elements"] = [{field: "Saved", "visible": True, "sensitive": False}]
    assert status(observation, {"text_present": "Saved"}) == "passed"


def test_legacy_unflagged_sources_retain_existing_postcondition_behavior():
    observation = {"elements": [{"name": "Saved"}]}
    assert status(observation, {"text_absent": "Missing"}) == "passed"
    assert status(observation, {"count": {"equals": 1}}) == "passed"


def test_file_target_never_finishes_from_a_vacuous_screen_absence(tmp_path):
    with closing(AgentRuntime(tmp_path / "tasks.sqlite", targets={"files": FileTarget()})) as runtime:
        task = runtime.submit({"goal": "verify archive", "target": "files", "roots": [str(tmp_path)],
            "allowed_tools": ["AC_workflow_manifest"],
            "success_criteria": [{"kind": "screen", "spec": {"text_absent": "Error"}}]})
        assert runtime.finish(task.task_id).state == "waiting_user"
        observation = FileTarget().observe()
        assert observation["semantic_observation"] is False
        assert status(observation, {"text_absent": "Error"}) == "unknown"


def test_desktop_bootstrap_has_no_semantic_screen_evidence(monkeypatch):
    target = DesktopTarget()
    monkeypatch.setattr(target, "_observation_window", lambda: None)
    observation = target.observe()
    assert observation["semantic_observation"] is False
    assert status(observation, {"text_absent": "Error"}) == "unknown"


def test_bounded_desktop_labels_keep_safe_matches_and_exclude_mask_placeholders(monkeypatch):
    from je_auto_control.utils.accessibility import accessibility_api
    controls = [AccessibilityElement("Saved", "button", (0, 0, 10, 10), process_id=2),
                AccessibilityElement("SECRET", "edit", (0, 10, 10, 10), process_id=2),
                AccessibilityElement("Foreign", "button", (0, 20, 10, 10), process_id=3)]
    target = DesktopTarget()
    monkeypatch.setattr(target, "_observation_window", lambda: (1, "Owned", 2))
    monkeypatch.setattr(target, "_check_foreground", lambda: (1, "Owned", 2))
    monkeypatch.setattr(accessibility_api, "list_accessibility_elements", lambda **_kwargs: controls)
    observation = target.observe()
    assert observation["semantic_observation"] is True and observation["text_redacted"] is True
    assert len(observation["elements"]) == 2
    assert "SECRET" not in str(observation)
    assert status(observation, {"text_present": "Saved"}) == "passed"
    for text in ("Missing", "Foreign", "[redacted]", "SECRET"):
        assert status(observation, {"text_absent": text}) == "unknown"
        assert status(observation, {"text_present": text}) == "unknown"


@pytest.mark.parametrize("frames", [[], [{"selector": "#frame", "error": "Unavailable"}]])
def test_bounded_browser_previews_never_prove_global_absence(frames):
    target = BrowserTarget()
    target._session = SimpleNamespace(observe=lambda: {"text": "Other body text", "frames": frames,
        "elements": [{"selector": "#save", "text": "Saved", "is_visible": True, "is_enabled": True},
                     {"selector": "#hidden", "text": "Hidden", "is_visible": False}]})
    observation = target.observe()
    assert observation["semantic_observation"] is True and observation["text_redacted"] is True
    assert status(observation, {"text_present": "Saved"}) == "passed"
    assert status(observation, {"text_absent": "Saved"}) == "failed"
    for text in ("Missing", "Other body text", "Hidden"):
        assert status(observation, {"text_absent": text}) == "unknown"
        assert status(observation, {"text_present": text}) == "unknown"
