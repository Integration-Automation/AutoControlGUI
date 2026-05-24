"""Computer-Use tab: launch Anthropic's closed-loop agent from the GUI."""
import json
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.agent.backends import AgentBackendError
from je_auto_control.utils.agent.computer_use import (
    result_to_dict, run_computer_use,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class _ComputerUseWorker(QObject):
    """Runs ``run_computer_use`` off the Qt thread."""

    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, params: dict) -> None:
        super().__init__()
        self._params = dict(params)

    def run(self) -> None:
        try:
            result = run_computer_use(**self._params)
        except (AgentBackendError, ValueError, RuntimeError) as error:
            self.failed.emit(f"{type(error).__name__}: {error}")
            return
        self.finished.emit(result_to_dict(result))


class ComputerUseTab(TranslatableMixin, QWidget):
    """Drive Anthropic Computer-Use against the current screen."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._goal_input = QLineEdit()
        self._model_input = QLineEdit("claude-opus-4-7")
        self._max_steps = QSpinBox()
        self._max_steps.setRange(1, 200)
        self._max_steps.setValue(25)
        self._wall_seconds = QSpinBox()
        self._wall_seconds.setRange(10, 3600)
        self._wall_seconds.setValue(300)
        self._max_tokens = QSpinBox()
        self._max_tokens.setRange(64, 8192)
        self._max_tokens.setValue(1024)
        self._run_btn = QPushButton()
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._status = QLabel()
        self._thread: Optional[QThread] = None
        self._worker: Optional[_ComputerUseWorker] = None
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_translations()

    # --- layout ----------------------------------------------------

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        form = QFormLayout()
        self._goal_label = QLabel()
        self._model_label = QLabel()
        self._max_steps_label = QLabel()
        self._wall_seconds_label = QLabel()
        self._max_tokens_label = QLabel()
        form.addRow(self._goal_label, self._goal_input)
        form.addRow(self._model_label, self._model_input)
        form.addRow(self._max_steps_label, self._max_steps)
        form.addRow(self._wall_seconds_label, self._wall_seconds)
        form.addRow(self._max_tokens_label, self._max_tokens)
        root.addLayout(form)
        btn_row = QHBoxLayout()
        self._run_btn.clicked.connect(self._on_run)
        btn_row.addWidget(self._run_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)
        root.addWidget(self._status)
        self._output_label = QLabel()
        root.addWidget(self._output_label)
        root.addWidget(self._output, stretch=1)
        self._apply_translations()

    def _apply_translations(self) -> None:
        self._goal_label.setText(_t("computer_use_goal_label"))
        self._model_label.setText(_t("computer_use_model_label"))
        self._max_steps_label.setText(_t("computer_use_max_steps_label"))
        self._wall_seconds_label.setText(_t("computer_use_wall_seconds_label"))
        self._max_tokens_label.setText(_t("computer_use_max_tokens_label"))
        self._output_label.setText(_t("computer_use_output_label"))
        self._goal_input.setPlaceholderText(_t("computer_use_goal_placeholder"))
        self._run_btn.setText(_t("computer_use_run_btn"))

    # --- run path --------------------------------------------------

    def _on_run(self) -> None:
        goal = self._goal_input.text().strip()
        if not goal:
            QMessageBox.warning(
                self, _t("computer_use_run_btn"),
                _t("computer_use_goal_required"),
            )
            return
        if self._thread is not None and self._thread.isRunning():
            self._status.setText(_t("computer_use_already_running"))
            return
        params = {
            "goal": goal,
            "model": self._model_input.text().strip() or "claude-opus-4-7",
            "max_steps": int(self._max_steps.value()),
            "wall_seconds": float(self._wall_seconds.value()),
            "max_tokens": int(self._max_tokens.value()),
        }
        self._status.setText(_t("computer_use_running"))
        self._run_btn.setEnabled(False)
        self._spawn_worker(params)

    def _spawn_worker(self, params: dict) -> None:
        thread = QThread(self)
        worker = _ComputerUseWorker(params)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_worker_finished)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_worker_finished(self, data: dict) -> None:
        self._run_btn.setEnabled(True)
        ok = bool(data.get("succeeded"))
        key = "computer_use_success" if ok else "computer_use_failure"
        self._status.setText(_t(key))
        self._output.setPlainText(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
        )
        self._thread = None
        self._worker = None

    def _on_worker_failed(self, message: str) -> None:
        self._run_btn.setEnabled(True)
        self._status.setText(f"{_t('computer_use_error')}: {message}")
        self._thread = None
        self._worker = None


__all__ = ["ComputerUseTab"]
