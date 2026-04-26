"""LLM Planner tab: describe a task in plain language → preview → run.

The tab calls the headless ``plan_actions`` helper, shows the resulting
JSON action list for review, and lets the user execute it through the
shared global executor. Long calls run on a background ``QThread`` so the
UI stays responsive.
"""
import json
from typing import List, Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.executor.action_executor import execute_action, executor
from je_auto_control.utils.llm.backends.base import LLMNotAvailableError
from je_auto_control.utils.llm.planner import LLMPlanError, plan_actions


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class _PlanWorker(QObject):
    """Runs ``plan_actions`` off the GUI thread and emits the result."""

    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, description: str, model: Optional[str],
                 known_commands: List[str]) -> None:
        super().__init__()
        self._description = description
        self._model = model
        self._known = list(known_commands)

    def run(self) -> None:
        try:
            actions = plan_actions(
                self._description,
                known_commands=self._known,
                model=self._model,
            )
        except LLMNotAvailableError as error:
            self.failed.emit(str(error))
        except (LLMPlanError, ValueError, OSError, RuntimeError) as error:
            self.failed.emit(f"{type(error).__name__}: {error}")
        else:
            self.finished.emit(actions)


class LLMPlannerTab(TranslatableMixin, QWidget):
    """Translate plain-language descriptions into runnable AC_* scripts."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._description = QTextEdit()
        self._model = QLineEdit()
        self._actions_view = QTextEdit()
        self._actions_view.setReadOnly(True)
        self._result_view = QTextEdit()
        self._result_view.setReadOnly(True)
        self._status = QLabel()
        self._planned_actions: Optional[list] = None
        self._plan_btn: Optional[QPushButton] = None
        self._run_btn: Optional[QPushButton] = None
        self._plan_thread: Optional[QThread] = None
        self._plan_worker: Optional[_PlanWorker] = None
        self._build_layout()
        self._apply_placeholders()
        self._set_run_enabled(False)

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_placeholders()

    def _apply_placeholders(self) -> None:
        self._description.setPlaceholderText(_t("llm_desc_placeholder"))
        self._model.setPlaceholderText(_t("llm_model_placeholder"))

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)

        desc_group = self._tr(QGroupBox(), "llm_desc_group")
        desc_layout = QVBoxLayout()
        desc_layout.addWidget(self._description)
        model_row = QHBoxLayout()
        model_row.addWidget(self._tr(QLabel(), "llm_model_label"))
        model_row.addWidget(self._model, stretch=1)
        desc_layout.addLayout(model_row)
        btn_row = QHBoxLayout()
        self._plan_btn = self._tr(QPushButton(), "llm_plan_btn")
        self._plan_btn.clicked.connect(self._on_plan)
        self._run_btn = self._tr(QPushButton(), "llm_run_btn")
        self._run_btn.clicked.connect(self._on_run)
        btn_row.addWidget(self._plan_btn)
        btn_row.addWidget(self._run_btn)
        btn_row.addStretch()
        desc_layout.addLayout(btn_row)
        desc_group.setLayout(desc_layout)
        root.addWidget(desc_group)

        actions_group = self._tr(QGroupBox(), "llm_plan_group")
        actions_layout = QVBoxLayout()
        actions_layout.addWidget(self._actions_view)
        actions_group.setLayout(actions_layout)
        root.addWidget(actions_group, stretch=1)

        result_group = self._tr(QGroupBox(), "llm_result_group")
        result_layout = QVBoxLayout()
        result_layout.addWidget(self._result_view)
        result_group.setLayout(result_layout)
        root.addWidget(result_group, stretch=1)

        root.addWidget(self._status)

    def _set_run_enabled(self, enabled: bool) -> None:
        if self._run_btn is not None:
            self._run_btn.setEnabled(enabled)

    def _on_plan(self) -> None:
        description = self._description.toPlainText().strip()
        if not description:
            self._status.setText(_t("llm_desc_required"))
            return
        if self._plan_thread is not None and self._plan_thread.isRunning():
            return
        model = self._model.text().strip() or None
        if self._plan_btn is not None:
            self._plan_btn.setEnabled(False)
        self._status.setText(_t("llm_planning"))
        self._actions_view.clear()
        self._planned_actions = None
        self._set_run_enabled(False)
        worker = _PlanWorker(description, model, sorted(executor.known_commands()))
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_plan_finished)
        worker.failed.connect(self._on_plan_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._on_thread_done)
        self._plan_worker = worker
        self._plan_thread = thread
        thread.start()

    def _on_plan_finished(self, actions: list) -> None:
        self._planned_actions = actions
        self._actions_view.setText(
            json.dumps(actions, indent=2, ensure_ascii=False)
        )
        self._status.setText(
            _t("llm_plan_count").replace("{n}", str(len(actions)))
        )
        self._set_run_enabled(bool(actions))

    def _on_plan_failed(self, message: str) -> None:
        self._planned_actions = None
        self._set_run_enabled(False)
        QMessageBox.warning(self, _t("llm_plan_btn"), message)
        self._status.setText(message)

    def _on_thread_done(self) -> None:
        if self._plan_thread is not None:
            self._plan_thread.deleteLater()
        if self._plan_worker is not None:
            self._plan_worker.deleteLater()
        self._plan_thread = None
        self._plan_worker = None
        if self._plan_btn is not None:
            self._plan_btn.setEnabled(True)

    def _on_run(self) -> None:
        if not self._planned_actions:
            self._status.setText(_t("llm_no_plan"))
            return
        self._status.setText(_t("llm_running"))
        try:
            record = execute_action(self._planned_actions)
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, _t("llm_run_btn"), str(error))
            self._status.setText(str(error))
            return
        self._result_view.setText(
            json.dumps(record, indent=2, ensure_ascii=False, default=str)
        )
        self._status.setText(_t("llm_run_done"))
