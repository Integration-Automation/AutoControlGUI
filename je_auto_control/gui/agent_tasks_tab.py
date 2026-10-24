"""Managed task workspace; background service ownership is independent of widget lifetime."""
from __future__ import annotations

import json
from functools import partial
from typing import Any
from pathlib import Path

from PySide6.QtWidgets import (  # pylint: disable=no-name-in-module  # reason: compiled Qt exports, tested offscreen
    QComboBox, QFormLayout, QLabel, QLineEdit, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.task_controller import TaskController, TaskOutcome
from je_auto_control.gui.agent_observation_view import AgentObservationView
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.api import start_agent_runtime, stop_agent_runtime
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, AgentActionRequest
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.workflow_specs import draft_agent_workflow, WORKFLOWS
from je_auto_control.utils.agent_runtime.task_triggers import OPERATIONS as TRIGGER_OPERATIONS
from je_auto_control.utils.agent_runtime.task_skills import OPERATIONS as SKILL_OPERATIONS
from je_auto_control.utils.agent_runtime.trigger_config import KINDS as TRIGGER_KINDS
from je_auto_control.utils.agent_runtime.target_profiles import OPERATIONS as TARGET_OPERATIONS
from je_auto_control.utils.agent_runtime.target_config import AgentTargetProfile
from je_auto_control.utils.agent_runtime.browser_commands import (
    BROWSER_CORE_TOOLS, BROWSER_ADAPTER_TOOLS, BROWSER_ELEMENT_TOOLS,
)
from je_auto_control.utils.exception.cancellation import CancellationToken


def _translate(key: str) -> str:
    return language_wrapper.translate(key, key)


def _request(operation: str, payload: dict, token: CancellationToken) -> dict:
    token.checkpoint()
    if operation == "start":
        return start_agent_runtime()
    if operation == "stop":
        return stop_agent_runtime()
    if operation == "draft":
        return {"draft": draft_agent_workflow(payload["workflow"], payload["config"])}
    return AgentRuntimeClient().call(operation, payload or None)


class AgentTasksTab(TranslatableMixin, QWidget):
    """Review authorization and completion criteria before submitting a managed task."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._controller = TaskController(self)
        self._handle: Any = None
        self._view_task = ""
        self._lookup_view: tuple[str, str] | None = None
        self._labels: list[tuple[QLabel, str]] = []
        self._pages = QTabWidget()
        self._page_keys: list[str] = []
        self._setup_fields()
        self._setup_pages()
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._table = QTableWidget(0, 4)
        self._table.cellClicked.connect(self._select)
        self._status = QLabel()
        self._task_id.textChanged.connect(self._clear_observation)
        layout = QVBoxLayout(self)
        layout.addWidget(self._task_id)
        layout.addWidget(self._pages)
        layout.addWidget(self._status)
        layout.addWidget(self._table)
        layout.addWidget(self._output)
        self.retranslate()

    def _setup_fields(self) -> None:
        self._goal, self._target, self._task_id = QLineEdit(), QLineEdit("local-desktop"), QLineEdit()
        self._recovery_note = QLineEdit()
        owner_policy = QComboBox(self)
        owner_policy.setObjectName("agent_recovery_owner_policy")
        for name in ("caller", "source_owner"):
            owner_policy.addItem(_translate("agent_owner_" + name), name)
        self._review = QPlainTextEdit('{"action_id": "", "decision": "not_applied", "note": ""}')
        remainder = QPlainTextEdit("{}", self)
        remainder.setObjectName("agent_remainder_request")
        self._skill_operation, self._skill_request = QComboBox(), QPlainTextEdit("{}")
        for name in SKILL_OPERATIONS:
            self._skill_operation.addItem(_translate("agent_skill_" + name), name)
        self._mode = QComboBox()
        self._mode.addItems(["external", "skill", "ollama"])
        self._workflow = QComboBox()
        self._workflow.addItems(list(WORKFLOWS))
        self._workflow_config = QPlainTextEdit("{}")
        self._request_key, self._trigger_id, self._event_key = QLineEdit(), QLineEdit(), QLineEdit()
        self._trigger_operation, self._trigger_kind = QComboBox(), QComboBox()
        for name in TRIGGER_OPERATIONS:
            self._trigger_operation.addItem(_translate("agent_trigger_" + name), name)
        for name in TRIGGER_KINDS:
            self._trigger_kind.addItem(_translate("agent_trigger_kind_" + name), name)
        self._trigger_config = QPlainTextEdit('{"seconds": 300}')
        self._scope = QPlainTextEdit()
        self._scope.setPlainText(json.dumps({"apps": [], "roots": [], "allowed_tools": ["AC_control_get_value"],
                                             "success_criteria": [{"kind": "result_equals", "key": "value",
                                                                    "value": "expected"}]}, indent=2))
        self._action = QPlainTextEdit()
        self._action.setPlainText(json.dumps({"tool": "AC_click_mouse", "arguments": {"mouse_keycode": "left"},
                                              "observation_id": ""}, indent=2))
        self._observation = AgentObservationView()
        self._observation.picked.connect(self._pick_reference)
        self._target_operation, self._target_request = QComboBox(), QPlainTextEdit("{}")
        for name in TARGET_OPERATIONS:
            self._target_operation.addItem(_translate("agent_target_" + name), name)

    def _setup_pages(self) -> None:
        self._page("agent_page_task", (("agent_goal", self._goal), ("agent_target", self._target),
                   ("agent_mode", self._mode), ("agent_scope", self._scope),
                   ("agent_request_key", self._request_key)))
        self._page("agent_page_workflow", (("agent_workflow", self._workflow),
                   ("agent_workflow_config", self._workflow_config)))
        self._page("agent_page_triggers", (("agent_trigger_id", self._trigger_id),
                   ("agent_trigger_operation", self._trigger_operation), ("agent_trigger_kind", self._trigger_kind),
                   ("agent_event_key", self._event_key), ("agent_trigger_config", self._trigger_config)))
        self._page("agent_page_skills", (("agent_skill_operation", self._skill_operation),
                   ("agent_skill_request", self._skill_request)))
        self._page("agent_page_targets", (("agent_target_operation", self._target_operation),
                   ("agent_target_request", self._target_request)))
        self._page("agent_page_recovery", (("agent_recovery_note", self._recovery_note),
                   ("agent_owner_policy", self._owner_policy),
                   ("agent_review", self._review), ("agent_remainder_request", self._remainder_request)))
        self._page("agent_page_observation", (("agent_action", self._action),))
        self._pages.widget(self._pages.count() - 1).layout().addWidget(self._observation)

    def _page(self, key: str, fields: tuple) -> None:
        page = QWidget()
        form = QFormLayout()
        for label_key, control in fields:
            label = QLabel()
            self._labels.append((label, label_key))
            form.addRow(label, control)
        layout = QVBoxLayout(page)
        layout.addLayout(form)
        self._pages.addTab(page, _translate(key))
        self._page_keys.append(key)

    def retranslate(self) -> None:
        """Translate cached controls without starting a service or reading task data."""
        TranslatableMixin.retranslate(self)
        for label, key in self._labels:
            label.setText(_translate(key))
        self._table.setHorizontalHeaderLabels([_translate(key) for key in
                                                ("agent_task_id", "agent_goal", "agent_state", "agent_reason")])
        self._status.setText(_translate("agent_background_note"))
        self._task_id.setPlaceholderText(_translate("agent_task_id"))
        for index, key in enumerate(self._page_keys):
            self._pages.setTabText(index, _translate(key))
        self._observation.retranslate()
        for combo, prefix in ((self._trigger_operation, "agent_trigger_"), (self._trigger_kind, "agent_trigger_kind_"),
                              (self._owner_policy, "agent_owner_")):
            for index in range(combo.count()):
                combo.setItemText(index, _translate(prefix + combo.itemData(index)))
        for index in range(self._skill_operation.count()):
            self._skill_operation.setItemText(index, _translate("agent_skill_" + self._skill_operation.itemData(index)))
        for index in range(self._target_operation.count()):
            label = _translate("agent_target_" + self._target_operation.itemData(index))
            self._target_operation.setItemText(index, label)

    def menu_actions(self) -> list:
        """Expose lifecycle commands through the common Actions menu."""
        return [("agent_start", partial(self._dispatch, "start")),
                ("agent_stop_service", partial(self._dispatch, "stop")),
                ("agent_stop_all", partial(self._dispatch, "stop_all", {})),
                ("agent_preview", self._preview),
                ("agent_act", self._act),
                ("agent_reconcile", self._reconcile),
                ("agent_remainder_preview", self._preview_remainder),
                ("agent_remainder_create", self._create_remainder),
                ("agent_reauthorize_preview", partial(self._preview_remainder, "review_authorization")),
                ("agent_reauthorize_create", partial(self._create_remainder, "create_authorized")),
                ("agent_completion_preview", partial(self._preview_remainder, "preview_completion")),
                ("agent_completion_create", partial(self._create_remainder, "create_completion")),
                ("agent_recover_target", self._recover_target),
                ("agent_prune", partial(self._dispatch, "prune", {})),
                ("agent_trigger_apply", self._trigger_apply),
                ("agent_trigger_list", partial(self._dispatch, "trigger", {"operation": "list"})),
                ("agent_skill_apply", self._skill_apply),
                ('agent_skill_completion_example', self._skill_completion_example),
                ("agent_skill_list", partial(self._dispatch, "skill", {"operation": "list"})),
                ("agent_target_apply", self._target_apply),
                ("agent_browser_example", self._browser_example),
                ("agent_browser_completion_example", self._browser_completion_example),
                ("agent_browser_files_example", self._browser_files_example),
                ("agent_target_list", partial(self._dispatch, "targets", {})),
                ("agent_submit", self._submit), ("agent_refresh", partial(self._dispatch, "list")),
                ("agent_lookup", self._lookup),
                *[("agent_" + name, partial(self._dispatch, name)) for name in
                  ("get", "observe", "finish", "pause", "resume", "cancel", "receipts")]]

    def _lookup(self) -> None:
        self._dispatch("lookup", {"idempotency_key": self._request_key.text()})

    def _preview_remainder(self, operation: str = "preview") -> None:
        self._remainder_request.setPlainText("{}")
        request = {"task_id": self._task_id.text()}
        if self._owner_policy.currentData() == "source_owner":
            request["owner_policy"] = "source_owner"
        self._dispatch("recovery", {"operation": operation, "request": request})

    @property
    def _owner_policy(self) -> QComboBox:
        policy = self.findChild(QComboBox, "agent_recovery_owner_policy")
        if policy is None:
            raise AgentTaskError("recovery owner selection is unavailable")
        return policy

    @property
    def _remainder_request(self) -> QPlainTextEdit:
        editor = self.findChild(QPlainTextEdit, "agent_remainder_request")
        if editor is None:
            raise AgentTaskError("recovery editor is unavailable")
        return editor

    def _create_remainder(self, operation: str = "create") -> None:
        try:
            request = json.loads(self._remainder_request.toPlainText())
            if not isinstance(request, dict) or request.get("task_id") != self._task_id.text():
                raise AgentTaskError("preview and review the selected task's remaining steps first")
            if request.get("owner_policy", "caller") != self._owner_policy.currentData():
                raise AgentTaskError("recovery owner selection changed; preview and review again")
        except (ValueError, TypeError) as error:
            self._status.setText(str(error))
            return
        self._dispatch("recovery", {"operation": operation, "request": request})

    def _preview(self) -> None:
        try:
            config = json.loads(self._workflow_config.toPlainText())
        except (ValueError, TypeError) as error:
            self._status.setText(str(error))
            return
        self._dispatch("draft", {"workflow": self._workflow.currentText(), "config": config})

    def _browser_example(self) -> None:
        profile = AgentTargetProfile(name="reviewed-browser", kind="browser",
                                     allowed_tools=tuple(sorted(BROWSER_CORE_TOOLS)),
                                     settings={"allowed_origins": ["https://example.invalid"]})
        self._target_request.setPlainText(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2))
        self._pages.setCurrentIndex(self._page_keys.index("agent_page_targets"))

    def _browser_completion_example(self) -> None:
        spec = AgentTaskSpec(goal="Review browser completion", target="reviewed-browser",
            allowed_tools=("AC_browser_navigate", "AC_browser_read"),
            options={"allowed_origins": ["https://example.invalid"]},
            success_criteria=({"kind": "browser", "operation": "text", "selector": "#confirmation",
                               "value": "expected"},)).to_dict()
        self._target.setText(spec.pop("target"))
        self._mode.setCurrentText(spec.pop("mode"))
        spec.pop("goal")
        self._scope.setPlainText(json.dumps(spec, ensure_ascii=False, indent=2))
        self._pages.setCurrentIndex(self._page_keys.index("agent_page_task"))

    def _browser_files_example(self) -> None:
        root = str(Path.cwd() / "agent-files")
        profile = AgentTargetProfile(name="reviewed-browser", kind="browser", roots=(root,),
            allowed_tools=tuple(sorted(BROWSER_ADAPTER_TOOLS)),
            settings={"allowed_origins": ["https://example.invalid"]})
        self._target_request.setPlainText(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2))
        self._workflow.setCurrentText("download_archive")
        self._workflow_config.setPlainText(json.dumps({"backend": "browser", "roots": [root],
            "directory": root, "url": "https://example.invalid/reports", "target": "reviewed-browser",
            "allowed_origins": ["https://example.invalid"],
            "files": [{"name": "report.bin", "selector": "#download"}]}, ensure_ascii=False, indent=2))
        self._action.setPlainText(json.dumps({"tool": "AC_browser_upload", "arguments": {
            "selector": "input[type=file]", "path": str(Path(root) / "upload.bin"), "sha256": ""}}, indent=2))
        self._pages.setCurrentIndex(self._page_keys.index("agent_page_targets"))

    def _clear_observation(self, _task_id: str = "") -> None:
        self._observation.clear()
        self._remainder_request.setPlainText("{}")

    def _pick_reference(self, reference: dict) -> None:
        try:
            action = json.loads(self._action.toPlainText())
            if not isinstance(action, dict) or not isinstance(action.get("arguments", {}), dict):
                raise AgentTaskError("action must contain an arguments object")
            excluded = {"x", "y"}
            if action.get("tool") in BROWSER_ELEMENT_TOOLS:
                excluded |= {"selector", "frame"}
            arguments = {key: value for key, value in action.get("arguments", {}).items() if key not in excluded}
            action.update(arguments=arguments, reference=reference, observation_id=self._observation.observation_id)
            self._action.setPlainText(json.dumps(AgentActionRequest.from_dict(action).to_dict(),
                                                  ensure_ascii=False, indent=2))
        except (ValueError, TypeError) as error:
            self._status.setText(str(error))

    def _act(self) -> None:
        try:
            action = AgentActionRequest.from_dict(json.loads(self._action.toPlainText()))
            if not self._observation.observation_id or action.observation_id != self._observation.observation_id:
                raise AgentTaskError("observe the selected task before submitting its action")
        except (ValueError, TypeError) as error:
            self._status.setText(str(error))
            return
        self._dispatch("act", {"task_id": self._task_id.text(), "action": action.to_dict()})
        self._clear_observation()

    def _reconcile(self) -> None:
        try:
            review = json.loads(self._review.toPlainText())
        except (ValueError, TypeError) as error:
            self._status.setText(str(error))
            return
        self._dispatch("reconcile", {"task_id": self._task_id.text(), "review": review})

    def _recover_target(self) -> None:
        self._dispatch("recover_target", {"target": self._target.text(), "note": self._recovery_note.text()})

    def _skill_apply(self) -> None:
        try:
            request = json.loads(self._skill_request.toPlainText())
        except (ValueError, TypeError) as error:
            self._status.setText(str(error))
            return
        self._dispatch("skill", {"operation": self._skill_operation.currentData(), "request": request})

    def _skill_completion_example(self) -> None:
        self._skill_operation.setCurrentIndex(self._skill_operation.findData('accept'))
        request = {'candidate_id': '<candidate-id>', 'task_id': '<original-validation-task-id>',
                   'completion_task_id': self._task_id.text() or '<completion-task-id>',
                   'expected_version': 0, 'note': ''}
        self._skill_request.setPlainText(json.dumps(request, ensure_ascii=False, indent=2))
        self._pages.setCurrentIndex(self._page_keys.index('agent_page_skills'))

    def _target_apply(self) -> None:
        try:
            request = json.loads(self._target_request.toPlainText())
        except (ValueError, TypeError) as error:
            self._status.setText(str(error))
            return
        self._dispatch("target", {"operation": self._target_operation.currentData(), "request": request})

    def _submit(self) -> None:
        try:
            payload: dict[str, Any] = {"spec": self._task_spec()}
            if self._request_key.text():
                payload["idempotency_key"] = self._request_key.text()
        except (ValueError, TypeError) as error:
            self._status.setText(str(error))
            return
        self._dispatch("submit", payload)

    def _task_spec(self) -> dict:
        spec = json.loads(self._scope.toPlainText())
        return AgentTaskSpec.from_dict({**spec, "goal": self._goal.text(), "target": self._target.text(),
                                        "mode": self._mode.currentText()}).to_dict()

    def _trigger_apply(self) -> None:
        operation = self._trigger_operation.currentData()
        try:
            request = self._trigger_request(operation)
        except (ValueError, TypeError) as error:
            self._status.setText(str(error))
            return
        if operation == "review_authorization":
            self._trigger_config.setPlainText("{}")
        self._dispatch("trigger", {"operation": operation, "request": request})

    def _trigger_request(self, operation: str) -> dict:
        if operation == "list":
            return {}
        if operation == "register":
            return {"kind": self._trigger_kind.currentData(), "config": json.loads(self._trigger_config.toPlainText()),
                    "spec": self._task_spec()}
        if operation == "create_authorized":
            request = json.loads(self._trigger_config.toPlainText())
            if not isinstance(request, dict) or request.get("trigger_id") != self._trigger_id.text():
                raise ValueError("reviewed trigger request must match the selected registration")
            return request
        request = {"trigger_id": self._trigger_id.text()}
        if operation == "fire":
            request.update(event_key=self._event_key.text(), payload=json.loads(self._trigger_config.toPlainText()))
        return request

    def _dispatch(self, operation: str, payload: dict | None = None) -> None:
        if self._handle is not None and self._handle.outcome is None:
            if operation not in {"pause", "cancel", "stop", "stop_all"}:
                return
            self._handle.cancel()
        task_operation = operation not in {
            "start", "stop", "list", "stop_all", "prune", "targets", "target", "lookup"}
        default = {"task_id": self._task_id.text()} if task_operation else {}
        data = payload or default
        self._view_task = str(data.get("task_id", ""))
        if operation == "recovery":
            self._view_task = str(data["request"]["task_id"])
        if operation == "trigger" and "trigger_id" in data.get("request", {}):
            self._view_task = "trigger:" + str(data["request"]["trigger_id"])
        self._lookup_view = (self._request_key.text(), self._task_id.text()) if operation == "lookup" else None
        self._handle = self._controller.submit(partial(_request, operation, data), owner=self)
        self._handle.finished.connect(self._completed)

    def _completed(self, outcome: TaskOutcome) -> None:
        if self._handle is not None and outcome.task_id != self._handle.task_id:
            return
        if not self._view_current():
            return
        if self._lookup_view is not None and self._lookup_view != (self._request_key.text(), self._task_id.text()):
            return
        if outcome.status != "ok":
            self._status.setText(outcome.error or outcome.status)
            return
        result = outcome.value
        self._output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        if not isinstance(result, dict):
            return
        self._present_result(result)

    def _view_current(self) -> bool:
        if self._view_task.startswith("trigger:"):
            return self._view_task == "trigger:" + self._trigger_id.text()
        return not self._view_task or self._view_task == self._task_id.text()

    def _present_result(self, result: dict) -> None:
        self._present_lookup(result)
        if not self._present_trigger_authorization(result):
            return
        if "source_task" in result:
            self._present_remainder(result)
        elif isinstance(result.get("draft"), dict):
            draft = result["draft"]
            self._goal.setText(draft["goal"])
            self._target.setText(draft["target"])
            self._mode.setCurrentText(draft["mode"])
            self._scope.setPlainText(json.dumps(draft, ensure_ascii=False, indent=2))
        if "task_id" in result:
            self._task_id.setText(result["task_id"])
        self._present_observation(result)
        if "trigger_id" in result:
            self._trigger_id.setText(result["trigger_id"])
        rows = result.get("tasks", [])
        if "tasks" in result:
            self._table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                for column, name in enumerate(("task_id", "goal", "state", "reason")):
                    self._table.setItem(index, column, QTableWidgetItem(str(row.get(name, ""))))

    def _present_observation(self, result: dict) -> None:
        if "observation_id" in result:
            try:
                self._observation.present(result)
            except AgentTaskError as error:
                self._status.setText(str(error))

    def _present_trigger_authorization(self, result: dict) -> bool:
        if "trigger_id" not in result or "approval_required" not in result:
            return True
        if result["trigger_id"] != self._trigger_id.text():
            return False
        spec = result.get("spec")
        request = {"trigger_id": result["trigger_id"], "snapshot": result["snapshot"],
                   "authorization_review": result["authorization_review"], "spec": spec,
                   "note": ""} if isinstance(spec, dict) else {}
        self._trigger_config.setPlainText(json.dumps(request, ensure_ascii=False, indent=2))
        self._pages.setCurrentIndex(self._page_keys.index("agent_page_triggers"))
        return True

    def _present_lookup(self, result: dict) -> None:
        found = result.get("task")
        if result.get("found") is True and isinstance(found, dict) and isinstance(found.get("task_id"), str):
            self._task_id.setText(found["task_id"])

    def _present_remainder(self, result: dict) -> None:
        draft = result.get("draft")
        if not isinstance(draft, dict):
            draft = result.get("review_template")
        request = {"task_id": result["source_task"], "snapshot": result["snapshot"],
                   "spec": draft, "note": ""} if isinstance(draft, dict) else {}
        if isinstance(result.get("verification_spec"), dict):
            request = {"task_id": result["source_task"], "snapshot": result["snapshot"], "note": ""}
        if request and "authorization_review" in result:
            request["authorization_review"] = result["authorization_review"]
        if request and "ownership" in result:
            request.update(owner_policy="source_owner", ownership_review=result["ownership"]["review"])
        self._remainder_request.setPlainText(json.dumps(request, ensure_ascii=False, indent=2))
        self._pages.setCurrentIndex(self._page_keys.index("agent_page_recovery"))

    def _select(self, row: int, _column: int) -> None:
        item = self._table.item(row, 0)
        if item is not None:
            self._task_id.setText(item.text())
