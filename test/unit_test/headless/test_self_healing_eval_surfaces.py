"""The evaluation and template-revision features on every delivery surface.

Facade, ``AC_*`` commands, MCP tools, Script Builder schema and the GUI tab
must all reach the same headless code and return the same report.
"""
import json

import numpy as np
import pytest

import je_auto_control as ac
from je_auto_control.utils.cv2_utils.image_file import write_image
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.self_healing import template_revision as revision_mod

_COMMANDS = (
    "AC_self_heal_evaluate", "AC_self_heal_revision_propose",
    "AC_self_heal_revision_preview", "AC_self_heal_revision_accept",
    "AC_self_heal_revision_revert", "AC_self_heal_revision_list",
)
_FACADE = (
    "EvaluationSample", "HealingComparison", "HealingEvaluationError",
    "TemplateRevision", "TemplateRevisionError", "TemplateRevisionStore",
    "accept_template_revision", "evaluate_healing_dataset", "evaluate_locators",
    "heal_context", "list_template_revisions", "preview_template_revision",
    "propose_template_revision", "revert_template_revision",
    "template_match_strategy",
)


def _noise(seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 255, (20, 30), dtype=np.uint8)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A template, a candidate, a labelled dataset and an isolated revision store."""
    monkeypatch.setattr(revision_mod, "default_revision_root", lambda: tmp_path / "store")
    old, new = _noise(1), _noise(2)
    frame = np.full((100, 160), 128, dtype=np.uint8)
    frame[30:50, 60:90] = new
    write_image(tmp_path / "template.png", old)
    write_image(tmp_path / "candidate.png", new)
    write_image(tmp_path / "frame.png", frame)
    (tmp_path / "dataset.json").write_text(json.dumps({
        "samples": [{"id": "new-look", "frame": "frame.png", "template": "template.png",
                     "expected_box": [60, 30, 90, 50]}],
        "versions": {"old": {"threshold": 0.9}},
        "thresholds": {"old": {"min_correct": 1}},
    }), encoding="utf-8")
    return tmp_path


def _mcp(name: str):
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    return {tool.name: tool for tool in build_default_tool_registry()}[name]


def _counts(payload):
    """The report without its latency columns, which differ run to run."""
    return {name: {key: value for key, value in report.items() if not key.endswith("_ms")}
            for name, report in payload["versions"].items()}


def test_facade_exports_the_names():
    for name in _FACADE:
        assert name in ac.__all__, name
        assert hasattr(ac, name), name


def test_commands_are_registered_and_in_the_script_builder():
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    known = set(executor.known_commands())
    in_builder = {spec.command for spec in _build_specs()}
    for command in _COMMANDS:
        assert command in known, command
        assert command in in_builder, command


def test_executor_and_mcp_return_the_same_evaluation(workspace):
    dataset = str(workspace / "dataset.json")
    from_executor = executor.event_dict["AC_self_heal_evaluate"](dataset_path=dataset)
    from_mcp = _mcp("ac_self_heal_evaluate").handler(dataset_path=dataset)
    from_api = ac.evaluate_healing_dataset(dataset)
    for payload in (from_executor, from_mcp, from_api):
        assert payload["versions"]["old"]["miss"] == 1
        assert payload["violations"]
        assert payload["passed"] is False
    assert _counts(from_executor) == _counts(from_mcp) == _counts(from_api)


def test_evaluate_runs_from_a_json_action_list(workspace):
    record = executor.execute_action(
        [["AC_self_heal_evaluate", {"dataset_path": str(workspace / "dataset.json")}]])
    payload = next(iter(record.values()))
    assert payload["versions"]["old"]["total"] == 1


def test_revision_lifecycle_through_the_executor(workspace):
    events = executor.event_dict
    template = workspace / "template.png"
    before = template.read_bytes()
    proposed = events["AC_self_heal_revision_propose"](
        template_path=str(template), candidate_path=str(workspace / "candidate.png"))
    revision_id = proposed["revision_id"]
    assert template.read_bytes() == before
    with pytest.raises(ac.TemplateRevisionError):
        events["AC_self_heal_revision_accept"](revision_id=revision_id)
    preview = events["AC_self_heal_revision_preview"](
        revision_id=revision_id, dataset_path=str(workspace / "dataset.json"))
    assert preview["revision"]["validated"] is True
    assert events["AC_self_heal_revision_accept"](revision_id=revision_id)["status"] == "accepted"
    assert template.read_bytes() == (workspace / "candidate.png").read_bytes()
    assert events["AC_self_heal_revision_revert"](revision_id=revision_id)["status"] == "reverted"
    assert template.read_bytes() == before
    assert [item["revision_id"] for item in events["AC_self_heal_revision_list"]()] == [revision_id]


def test_revision_lifecycle_through_mcp(workspace):
    template = workspace / "template.png"
    before = template.read_bytes()
    revision_id = _mcp("ac_self_heal_revision_propose").handler(
        template_path=str(template),
        candidate_path=str(workspace / "candidate.png"))["revision_id"]
    preview = _mcp("ac_self_heal_revision_preview").handler(revision_id=revision_id)
    assert preview["comparison"] is None
    assert preview["revision"]["validated"] is False
    accepted = _mcp("ac_self_heal_revision_accept").handler(
        revision_id=revision_id, allow_unvalidated=True)
    assert accepted["status"] == "accepted"
    _mcp("ac_self_heal_revision_revert").handler(revision_id=revision_id)
    assert template.read_bytes() == before
    assert len(_mcp("ac_self_heal_revision_list").handler()) == 1
    assert _mcp("ac_self_heal_evaluate").annotations.read_only is True
    assert _mcp("ac_self_heal_revision_accept").annotations.destructive is True


def test_context_reaches_the_log_from_executor_and_mcp(tmp_path, monkeypatch):
    from je_auto_control.utils.executor import action_executor
    from je_auto_control.utils.self_healing import HealEventLog
    from je_auto_control.utils.self_healing import locator as locator_mod
    log = HealEventLog(tmp_path / "events.jsonl")
    monkeypatch.setattr(locator_mod, "default_heal_log", log)
    monkeypatch.setattr(locator_mod, "_try_image", lambda path, threshold: ((3, 4), None))
    monkeypatch.setattr(locator_mod, "_click_at", lambda coords, keycode: None)
    result = action_executor.executor.event_dict["AC_self_heal_click"](
        template_path="t.png", context={"locator_version": "v2", "run_id": "r1"})
    assert result["found"] is True
    assert result["action"] == "click"
    assert result["action_verified"] is None
    _mcp("ac_self_heal_locate").handler(
        template_path="t.png", context={"locator_version": "v3"})
    first, second = log.list_events()
    assert (first.locator_version, first.run_id) == ("v2", "r1")
    assert second.locator_version == "v3"
    assert second.run_id is None
    handler = _mcp("ac_self_heal_locate").handler
    with pytest.raises(ValueError):
        handler(template_path="t.png", context={"x": "y"})


# --- GUI: a thin shell over the same calls --------------------------------


@pytest.fixture
def tab(workspace):
    # QtWidgets, not the bare package: an image without libEGL imports
    # PySide6 and then fails on the widgets module.
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from je_auto_control.gui.self_healing_tab import SelfHealingTab
    widget = SelfHealingTab()
    yield widget
    widget.deleteLater()
    app.processEvents()


def test_tab_commands_are_menu_actions_with_translations(tab):
    from je_auto_control.gui.language_wrapper import (
        english, japanese, simplified_chinese, traditional_chinese,
    )
    actions = dict(tab.menu_actions())
    wanted = {"self_heal_evaluate", "self_heal_rev_propose", "self_heal_rev_preview",
              "self_heal_rev_accept", "self_heal_rev_revert", "self_heal_rev_list",
              "self_heal_browse_dataset", "self_heal_browse_candidate"}
    assert wanted <= set(actions)
    assert all(callable(actions[key]) for key in wanted)
    for module in (english, japanese, simplified_chinese, traditional_chinese):
        catalogue = next(value for value in vars(module).values()
                         if isinstance(value, dict) and "self_heal_refresh" in value)
        missing = [key for key in wanted | {"self_heal_col_action_verified"}
                   if key not in catalogue]
        assert missing == [], (module.__name__, missing)


def test_tab_evaluates_and_walks_a_revision(tab, workspace, monkeypatch):
    from je_auto_control.gui import self_healing_tab as module
    actions = dict(tab.menu_actions())
    template = workspace / "template.png"
    before = template.read_bytes()

    actions["self_heal_evaluate"]()                      # no dataset typed yet
    assert tab._report_view.toPlainText() == ""
    tab._dataset_input.setText(str(workspace / "dataset.json"))
    actions["self_heal_evaluate"]()
    shown = json.loads(tab._report_view.toPlainText())
    assert shown["versions"]["old"]["miss"] == 1
    assert shown["passed"] is False

    tab._template_input.setText(str(template))
    tab._candidate_input.setText(str(workspace / "candidate.png"))
    actions["self_heal_rev_propose"]()
    revision_id = tab._revision_input.text()
    assert len(revision_id) == 12
    assert template.read_bytes() == before

    # Not validated yet: the tab asks, and "No" leaves the template alone.
    monkeypatch.setattr(module.QMessageBox, "question",
                        lambda *_args, **_kwargs: module.QMessageBox.No)
    actions["self_heal_rev_accept"]()
    assert template.read_bytes() == before

    actions["self_heal_rev_preview"]()
    assert json.loads(tab._report_view.toPlainText())["revision"]["validated"] is True

    def no_prompt(*_args, **_kwargs):
        raise AssertionError("a validated revision must not prompt")

    monkeypatch.setattr(module.QMessageBox, "question", no_prompt)
    actions["self_heal_rev_accept"]()
    assert template.read_bytes() == (workspace / "candidate.png").read_bytes()
    actions["self_heal_rev_revert"]()
    assert template.read_bytes() == before
    actions["self_heal_rev_list"]()
    assert json.loads(tab._report_view.toPlainText())[0]["status"] == "reverted"


def test_tab_reports_errors_in_the_status(tab):
    tab._revision_input.setText("not-an-id")
    dict(tab.menu_actions())["self_heal_rev_revert"]()
    assert "not a revision id" in tab._status.text()
    tab._revision_input.setText("")
    dict(tab.menu_actions())["self_heal_rev_preview"]()
    assert tab._status.text()


def test_log_table_shows_version_and_verification(tab, tmp_path, monkeypatch):
    from je_auto_control.gui import self_healing_tab as module
    from je_auto_control.utils.self_healing import HealEvent, HealEventLog
    log = HealEventLog(tmp_path / "events.jsonl")
    log.append(HealEvent("t1", "vlm", [1, 2], 3.0, locator_version="v2",
                         action="click", action_verified=False))
    log.append(HealEvent("t2", "image", [1, 2], 3.0))
    monkeypatch.setattr(module, "default_heal_log", log)
    tab.refresh_log()
    assert tab._table.item(0, 6).text() == "v2"
    assert tab._table.item(0, 7).text() != ""
    assert tab._table.item(1, 7).text() == ""
