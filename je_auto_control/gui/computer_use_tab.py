"""Computer-Use tab: launch Anthropic's closed-loop agent from the GUI."""
import json
import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QFormLayout, QLabel, QLineEdit, QMessageBox,
    QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import WorkerHandle, start_worker
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

    def __init__(self, params: dict, stop_event: threading.Event) -> None:
        super().__init__()
        self._params = dict(params)
        self._stop_event = stop_event

    def request_stop(self) -> None:
        """End the run before its next step (thread-safe)."""
        self._stop_event.set()

    def run(self) -> None:
        try:
            result = run_computer_use(**self._params, stop_event=self._stop_event)
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
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._status = QLabel()
        self._thread: Optional[WorkerHandle] = None
        self._stop_event = threading.Event()
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_translations()

    # --- layout ----------------------------------------------------

    def _build_layout(self) -> None:
        # The run command runs from the Actions menu; the tab keeps only
        # the goal/model/limit inputs, the output view, and the status.
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

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("computer_use_run_btn", self._on_run),
            ("computer_use_stop_btn", self._on_stop),
        ]

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
        self._spawn_worker(params)

    def _spawn_worker(self, params: dict) -> None:
        self._stop_event = threading.Event()
        self._thread = start_worker(
            self, _ComputerUseWorker(params, self._stop_event),
            on_done=self._on_worker_finished,
            on_fail=self._on_worker_failed, on_thread_done=self._on_thread_done)

    def _on_stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._status.setText(_t("computer_use_stopping"))

    def _on_thread_done(self) -> None:
        self._thread = None

    def _on_worker_finished(self, data: dict) -> None:
        ok = bool(data.get("succeeded"))
        key = "computer_use_success" if ok else "computer_use_failure"
        self._status.setText(_t(key))
        self._output.setPlainText(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
        )

    def _on_worker_failed(self, message: str) -> None:
        self._status.setText(f"{_t('computer_use_error')}: {message}")


__all__ = ["ComputerUseTab"]
