"""Observation selection edits grounded requests without emitting desktop input."""
import base64
import io
import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QPointF, Qt  # noqa: E402  # reason: optional Qt after skip
from PySide6.QtGui import QMouseEvent  # noqa: E402  # reason: optional Qt after skip
from PySide6.QtWidgets import QApplication  # noqa: E402  # reason: optional Qt after skip

from je_auto_control.gui.agent_tasks_tab import AgentTasksTab  # noqa: E402  # reason: optional Qt after skip
from je_auto_control.gui.task_controller import TaskOutcome  # noqa: E402  # reason: optional Qt after skip


@pytest.fixture
def tab():
    import shiboken6
    app = QApplication.instance() or QApplication([])
    widget = AgentTasksTab()
    yield widget
    widget.close()
    shiboken6.delete(widget)
    app.processEvents()


def observation(task="task-a", frame="frame-a"):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (20, 10), "black").save(buffer, format="JPEG")
    return {"task_id": task, "observation_id": frame, "captured_at": 10,
            "data": {"identity": "fixture", "elements": [
                {"index": 0, "name": "Save", "role": "button", "bounds": [10, 20, 30, 40]}],
                "image": {"format": "jpeg", "redacted_by": "strict", "image_size": [20, 10],
                          "data": base64.b64encode(buffer.getvalue()).decode("ascii")}}}


def test_element_selection_only_edits_action_and_actions_submit_it(tab, monkeypatch):
    calls = []
    monkeypatch.setattr(tab, "_dispatch", lambda *args: calls.append(args))
    tab._present_result(observation())
    tab._observation._elements.cellClicked.emit(0, 0)
    action = json.loads(tab._action.toPlainText())
    assert action["observation_id"] == "frame-a"
    assert action["reference"] == {"element_index": 0}
    assert calls == []
    dict(tab.menu_actions())["agent_act"]()
    assert calls == [("act", {"task_id": "task-a", "action": action})]


def test_android_semantic_selection_uses_the_shared_action_without_native_input(tab, monkeypatch):
    from je_auto_control.utils.agent_runtime.observation_refs import resolve_action
    calls = []
    monkeypatch.setattr(tab, "_dispatch", lambda *args: calls.append(args))
    frame = observation()
    frame['data'] = {'identity': {'platform': 'android', 'coordinate_space': 'android_display', 'hierarchy': 'f' * 64},
                     'elements': [{'index': 0, 'native_id': '0/0', 'name': 'Save', 'role': 'button',
                                   'bounds': [10, 20, 30, 40], 'enabled': True, 'visible': True, 'actionable': True}],
                     'semantic_observation': True, 'text_redacted': False, 'text': 'Save'}
    tab._action.setPlainText(json.dumps({'tool': 'AC_android_tap', 'arguments': {'x': 1, 'y': 2},
                                        'observation_id': ''}))
    tab._present_result(frame)
    tab._observation._elements.cellClicked.emit(0, 0)
    action = json.loads(tab._action.toPlainText())
    assert action['tool'] == 'AC_android_tap' and action['arguments'] == {}
    assert calls == []
    resolved, _ground = resolve_action(action['tool'], action['arguments'], action['reference'], frame['data'])
    assert resolved == {'x': 25, 'y': 40}
    dict(tab.menu_actions())['agent_act']()
    assert calls == [('act', {'task_id': 'task-a', 'action': action})]


def test_browser_target_example_is_inert(tab, monkeypatch):
    from je_auto_control.utils.agent_runtime.target_config import AgentTargetProfile
    calls = []
    monkeypatch.setattr(tab, "_dispatch", lambda *args: calls.append(args))
    dict(tab.menu_actions())["agent_browser_example"]()
    configuration = AgentTargetProfile.from_dict(json.loads(tab._target_request.toPlainText()))
    assert configuration.kind == "browser"
    assert configuration.settings["allowed_origins"] == ("https://example.invalid:443",)
    assert calls == []


def test_browser_completion_example_edits_scope_without_starting_or_dispatching(tab, monkeypatch):
    from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
    from je_auto_control.utils.agent_runtime.policy import TaskPolicy
    calls = []
    monkeypatch.setattr(tab, "_dispatch", lambda *args: calls.append(args))
    dict(tab.menu_actions())["agent_browser_completion_example"]()
    scope = json.loads(tab._scope.toPlainText())
    spec = AgentTaskSpec.from_dict({**scope, "goal": "reviewed", "target": tab._target.text(),
                                    "mode": tab._mode.currentText()})
    TaskPolicy(spec)
    assert spec.success_criteria[0]["kind"] == "browser"
    assert "AC_browser_read" in spec.allowed_tools
    assert calls == []


def test_browser_file_examples_only_edit_reviewable_grants_and_workflow(tab, monkeypatch, tmp_path):
    from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
    from je_auto_control.utils.agent_runtime.target_config import AgentTargetProfile
    from je_auto_control.utils.agent_runtime.workflow_specs import draft_agent_workflow
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(tab, "_dispatch", lambda *args: calls.append(args))
    dict(tab.menu_actions())["agent_browser_files_example"]()
    profile = AgentTargetProfile.from_dict(json.loads(tab._target_request.toPlainText()))
    assert profile.roots == (str(tmp_path / "agent-files"),)
    draft = draft_agent_workflow("download_archive", json.loads(tab._workflow_config.toPlainText()))
    profile.check(AgentTaskSpec.from_dict(draft))
    assert json.loads(tab._action.toPlainText())["tool"] == "AC_browser_upload"
    assert calls == []
    assert not (tmp_path / "agent-files").exists()


def test_browser_dependency_probe_uses_the_shared_target_action(tab, monkeypatch):
    calls = []
    monkeypatch.setattr(tab, "_dispatch", lambda *args: calls.append(args))
    tab._target_operation.setCurrentIndex(tab._target_operation.findData("probe"))
    tab._target_request.setPlainText('{"name":"isolated-browser"}')
    dict(tab.menu_actions())["agent_target_apply"]()
    assert calls == [("target", {"operation": "probe", "request": {"name": "isolated-browser"}})]


def test_browser_dom_selection_replaces_locator_only(tab, monkeypatch):
    calls = []
    monkeypatch.setattr(tab, "_dispatch", lambda *args: calls.append(args))
    observed = observation()
    observed["data"]["elements"] = [{"index": 0, "name": "Save", "role": "button", "selector": "#save",
                                     "frame": "#form", "enabled": True, "visible": True}]
    tab._action.setPlainText(json.dumps({"tool": "AC_browser_click", "arguments": {"selector": "#old", "frame": ""},
                                       "observation_id": ""}))
    tab._present_result(observed)
    tab._observation._elements.cellClicked.emit(0, 0)
    action = json.loads(tab._action.toPlainText())
    assert action["arguments"] == {}
    assert action["reference"] == {"element_index": 0}
    assert "#save" in tab._observation._elements.item(0, 3).text()
    assert calls == []


def test_image_click_uses_unscaled_rendered_pixels_and_never_dispatches(tab, monkeypatch):
    calls = []
    monkeypatch.setattr(tab, "_dispatch", lambda *args: calls.append(args))
    tab._present_result(observation())
    preview = tab._observation._image
    assert preview.pixmap().devicePixelRatio() == 1.0
    assert (preview.width(), preview.height()) == (20, 10)
    event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(12, 7), QPointF(12, 7),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    preview.mousePressEvent(event)
    assert json.loads(tab._action.toPlainText())["reference"] == {"image_point": [12, 7]}
    assert calls == []


def test_changing_task_invalidates_frame_and_prevents_old_action(tab, monkeypatch):
    calls = []
    monkeypatch.setattr(tab, "_dispatch", lambda *args: calls.append(args))
    tab._present_result(observation())
    tab._task_id.setText("task-b")
    assert tab._observation._elements.rowCount() == 0
    assert tab._observation._image.pixmap().isNull()
    dict(tab.menu_actions())["agent_act"]()
    assert calls == []


def test_stale_view_reply_cannot_replace_new_task_selection(tab, monkeypatch):
    signal = SimpleNamespace(connect=lambda _slot: None)
    monkeypatch.setattr(tab._controller, "submit", lambda *_args, **_kwargs:
                        SimpleNamespace(task_id=17, finished=signal, outcome=None))
    tab._task_id.setText("task-a")
    tab._dispatch("observe")
    tab._task_id.setText("task-b")
    tab._completed(TaskOutcome(17, "ok", observation()))
    assert tab._task_id.text() == "task-b"
    assert tab._observation._elements.rowCount() == 0


def test_untrusted_image_clears_existing_preview(tab):
    tab._present_result(observation())
    image = observation(frame="frame-b")
    image["data"]["image"]["image_size"] = [2000, 1000]
    tab._present_result(image)
    assert tab._observation._image.pixmap().isNull()
    assert tab._observation._elements.rowCount() == 1


def test_new_frame_requires_reselection_before_reusing_an_old_index(tab, monkeypatch):
    calls = []
    monkeypatch.setattr(tab, "_dispatch", lambda *args: calls.append(args))
    tab._present_result(observation())
    tab._observation._elements.cellClicked.emit(0, 0)
    tab._present_result(observation(frame="frame-b"))
    dict(tab.menu_actions())["agent_act"]()
    assert calls == []
    tab._observation._elements.cellClicked.emit(0, 0)
    dict(tab.menu_actions())["agent_act"]()
    assert calls[0][1]["action"]["observation_id"] == "frame-b"


def test_pixel_selection_floors_fractional_positions_at_the_frame_edge(tab):
    tab._present_result(observation())
    preview = tab._observation._image
    event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(19.9, 9.9), QPointF(19.9, 9.9),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    preview.mousePressEvent(event)
    assert json.loads(tab._action.toPlainText())["reference"] == {"image_point": [19, 9]}


def test_malformed_action_cannot_escape_the_gui_dispatch_boundary(tab, monkeypatch):
    calls = []
    monkeypatch.setattr(tab, "_dispatch", lambda *args: calls.append(args))
    tab._present_result(observation())
    tab._action.setPlainText('{"tool":"AC_click_mouse","observation_id":"frame-a","unexpected":true}')
    dict(tab.menu_actions())["agent_act"]()
    assert calls == []
    assert tab._status.text()
