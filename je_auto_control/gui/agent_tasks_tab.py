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
    if operation in {"observe", "finish"}:
        from je_auto_control.utils.agent_runtime import observe_agent_task, finish_agent_task
        return {"observe": observe_agent_task, "finish": finish_agent_task}[operation](payload["task_id"])
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

    def menu_actions(self) -> list:
        """Expose lifecycle commands through the common Actions menu."""
        return [("agent_start", partial(self._dispatch, "start")),
                ("agent_stop_service", partial(self._dispatch, "stop")),
                ("agent_stop_all", partial(self._dispatch, "stop_all", {})),
                ("agent_preview", self._preview),
                ("agent_reconcile", self._reconcile),
                ("agent_prune", partial(self._dispatch, "prune", {})),
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
            spec = json.loads(self._scope.toPlainText())
            spec.update(goal=self._goal.text(), target=self._target.text(), mode=self._mode.currentText())
            validated = AgentTaskSpec.from_dict(spec)
        except (ValueError, TypeError) as error:
            self._status.setText(str(error))
            return
        self._dispatch("submit", {"spec": validated.to_dict()})

    def _dispatch(self, operation: str, payload: dict | None = None) -> None:
        if self._handle is not None and self._handle.outcome is None:
            return
        task_operation = operation not in {"start", "stop", "list", "stop_all", "prune"}
        default = {"task_id": self._task_id.text()} if task_operation else {}
        data = payload or default
        self._handle = self._controller.submit(partial(_request, operation, data), owner=self)
        self._handle.finished.connect(self._completed)

    def _completed(self, outcome: TaskOutcome) -> None:
        if outcome.status != "ok":
            self._status.setText(outcome.error or outcome.status)
            return
        result = outcome.value
        self._output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        if not isinstance(result, dict):
            return
        if "draft" in result:
            draft = result["draft"]
            self._goal.setText(draft["goal"])
            self._target.setText(draft["target"])
            self._mode.setCurrentText(draft["mode"])
            self._scope.setPlainText(json.dumps(draft, ensure_ascii=False, indent=2))
        if "task_id" in result:
            self._task_id.setText(result["task_id"])
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
