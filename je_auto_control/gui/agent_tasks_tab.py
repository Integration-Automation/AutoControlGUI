"""Managed task workspace; background service ownership is independent of widget lifetime."""
from __future__ import annotations

import json
from functools import partial
from typing import Any

from PySide6.QtWidgets import (  # pylint: disable=no-name-in-module  # reason: compiled Qt exports, tested offscreen
    QComboBox, QFormLayout, QLabel, QLineEdit, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.task_controller import TaskController, TaskOutcome
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.api import start_agent_runtime, stop_agent_runtime
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.workflow_specs import draft_agent_workflow, WORKFLOWS
from je_auto_control.utils.agent_runtime.task_triggers import OPERATIONS as TRIGGER_OPERATIONS
from je_auto_control.utils.agent_runtime.trigger_config import KINDS as TRIGGER_KINDS
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
        self._goal, self._target, self._task_id = QLineEdit(), QLineEdit("local-desktop"), QLineEdit()
        self._mode = QComboBox()
        self._mode.addItems(["external", "skill", "ollama"])
        self._workflow = QComboBox()
        self._workflow.addItems(list(WORKFLOWS))
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
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._table = QTableWidget(0, 4)
        self._table.cellClicked.connect(self._select)
        self._status = QLabel()
        self._labels: list[tuple[QLabel, str]] = []
        form = QFormLayout()
        for key, control in (("agent_goal", self._goal), ("agent_target", self._target),
                             ("agent_mode", self._mode), ("agent_scope", self._scope),
                             ("agent_workflow", self._workflow),
                             ("agent_request_key", self._request_key), ("agent_trigger_id", self._trigger_id),
                             ("agent_trigger_operation", self._trigger_operation),
                             ("agent_trigger_kind", self._trigger_kind), ("agent_event_key", self._event_key),
                             ("agent_trigger_config", self._trigger_config),
                             ("agent_task_id", self._task_id)):
            label = QLabel()
            self._labels.append((label, key))
            form.addRow(label, control)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._status)
        layout.addWidget(self._table)
        layout.addWidget(self._output)
        self.retranslate()

    def retranslate(self) -> None:
        """Translate cached controls without starting a service or reading task data."""
        TranslatableMixin.retranslate(self)
        for label, key in self._labels:
            label.setText(_translate(key))
        self._table.setHorizontalHeaderLabels([_translate(key) for key in
                                                ("agent_task_id", "agent_goal", "agent_state", "agent_reason")])
        self._status.setText(_translate("agent_background_note"))
        for combo, prefix in ((self._trigger_operation, "agent_trigger_"), (self._trigger_kind, "agent_trigger_kind_")):
            for index in range(combo.count()):
                combo.setItemText(index, _translate(prefix + combo.itemData(index)))

    def menu_actions(self) -> list:
        """Expose lifecycle commands through the common Actions menu."""
        return [("agent_start", partial(self._dispatch, "start")),
                ("agent_stop_service", partial(self._dispatch, "stop")),
                ("agent_stop_all", partial(self._dispatch, "stop_all", {})),
                ("agent_preview", self._preview),
                ("agent_reconcile", self._reconcile),
                ("agent_prune", partial(self._dispatch, "prune", {})),
                ("agent_trigger_apply", self._trigger_apply),
                ("agent_trigger_list", partial(self._dispatch, "trigger", {"operation": "list"})),
                ("agent_submit", self._submit), ("agent_refresh", partial(self._dispatch, "list")),
                *[("agent_" + name, partial(self._dispatch, name)) for name in
                  ("get", "observe", "finish", "pause", "resume", "cancel", "receipts")]]

    def _preview(self) -> None:
        try:
            config = json.loads(self._scope.toPlainText())
        except (ValueError, TypeError) as error:
            self._status.setText(str(error))
            return
        self._dispatch("draft", {"workflow": self._workflow.currentText(), "config": config})

    def _reconcile(self) -> None:
        try:
            review = json.loads(self._scope.toPlainText())
        except (ValueError, TypeError) as error:
            self._status.setText(str(error))
            return
        self._dispatch("reconcile", {"task_id": self._task_id.text(), "review": review})

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
        self._dispatch("trigger", {"operation": operation, "request": request})

    def _trigger_request(self, operation: str) -> dict:
        if operation == "list":
            return {}
        if operation == "register":
            return {"kind": self._trigger_kind.currentData(), "config": json.loads(self._trigger_config.toPlainText()),
                    "spec": self._task_spec()}
        request = {"trigger_id": self._trigger_id.text()}
        if operation == "fire":
            request.update(event_key=self._event_key.text(), payload=json.loads(self._trigger_config.toPlainText()))
        return request

    def _dispatch(self, operation: str, payload: dict | None = None) -> None:
        if self._handle is not None and self._handle.outcome is None:
            if operation not in {"pause", "cancel", "stop", "stop_all"}:
                return
            self._handle.cancel()
        task_operation = operation not in {"start", "stop", "list", "stop_all", "prune"}
        default = {"task_id": self._task_id.text()} if task_operation else {}
        data = payload or default
        self._handle = self._controller.submit(partial(_request, operation, data), owner=self)
        self._handle.finished.connect(self._completed)

    def _completed(self, outcome: TaskOutcome) -> None:
        if self._handle is not None and outcome.task_id != self._handle.task_id:
            return
        if outcome.status != "ok":
            self._status.setText(outcome.error or outcome.status)
            return
        result = outcome.value
        self._output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        if not isinstance(result, dict):
            return
        self._present_result(result)

    def _present_result(self, result: dict) -> None:
        if "draft" in result:
            draft = result["draft"]
            self._goal.setText(draft["goal"])
            self._target.setText(draft["target"])
            self._mode.setCurrentText(draft["mode"])
            self._scope.setPlainText(json.dumps(draft, ensure_ascii=False, indent=2))
        if "task_id" in result:
            self._task_id.setText(result["task_id"])
        if "trigger_id" in result:
            self._trigger_id.setText(result["trigger_id"])
        rows = result.get("tasks", [])
        if "tasks" in result:
            self._table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                for column, name in enumerate(("task_id", "goal", "state", "reason")):
                    self._table.setItem(index, column, QTableWidgetItem(str(row.get(name, ""))))

    def _select(self, row: int, _column: int) -> None:
        item = self._table.item(row, 0)
        if item is not None:
            self._task_id.setText(item.text())
