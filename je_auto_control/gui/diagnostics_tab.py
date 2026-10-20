"""Explicit, cancellable diagnostics run off the GUI thread and publish only to their live owner."""
from dataclasses import dataclass
from functools import partial
from typing import Callable, Literal, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QCloseEvent, QShowEvent
from PySide6.QtWidgets import (
    QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.diagnostics_capabilities import CapabilityView
from je_auto_control.gui.task_controller import TaskController, TaskHandle, TaskOutcome
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.diagnostics.diagnostics import DiagnosticsReport, run_diagnostics
from je_auto_control.utils.exception.cancellation import CancellationToken, TaskProgress
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.logging.secret_scope import scrub_secret_text
from je_auto_control.utils.rbac.policy import authorize_command
from je_auto_control.utils.run_history.run_outcome import _ordinary_error_text
from je_auto_control.wrapper.capabilities import BackendContext, probe_capabilities


_SEVERITY_COLOR = {
    "info": QColor("#1e8a3a"),
    "warn": QColor("#b08400"),
    "error": QColor("#c0392b"),
}


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


@dataclass
class _DiagnosticViewState:
    kind: Literal['idle', 'running', 'stopping', 'cancelled', 'error', 'result'] = 'idle'
    report: Optional[DiagnosticsReport] = None
    error: str = ''
    completed: int = 0
    total: int = 0
    closed: bool = False
    accept_result: bool = True


def _diagnostic_work(runner: Callable[[], DiagnosticsReport], token: CancellationToken) -> object:
    authorize_command('AC_diagnose')
    token.checkpoint()
    return runner()


class DiagnosticsTab(TranslatableMixin, QWidget):
    """Run :func:`run_diagnostics` and render the results."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._view = _DiagnosticViewState()
        self._task_controller = TaskController(self)
        self._active_task: Optional[TaskHandle] = None
        self._summary_label = QLabel(_t("diag_summary_idle"))
        self._summary_label.setTextFormat(Qt.TextFormat.PlainText)
        self._summary_label.setWordWrap(True)
        self._progress_label = QLabel()
        self._progress_label.setWordWrap(True)
        self._capability_view = CapabilityView()
        self._table = QTableWidget(0, 4)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch,
        )
        self._build_layout()
        self._apply_table_headers()

    def _build_layout(self) -> None:
        # The run command runs from the Actions menu; the tab keeps only
        # the summary label and the results table.
        root = QVBoxLayout(self)
        root.addWidget(self._capability_view)
        root.addWidget(self._summary_label)
        root.addWidget(self._progress_label)
        root.addWidget(self._table, stretch=1)

    def menu_actions(self) -> list[tuple[str, Callable[[], None]]]:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("diag_probe", self._probe_capabilities),
            ("diag_run", self._refresh),
            ("diag_stop", self._stop),
        ]

    def retranslate(self) -> None:
        """Translate idle instructions and headers without starting a diagnostic run."""
        super().retranslate()
        self._apply_table_headers()
        self._capability_view.retranslate()
        self._render_summary()
        if self._view.report is not None:
            self._fill_table(self._view.report)

    def _probe_capabilities(self) -> None:
        snapshot = probe_capabilities(BackendContext.current())
        self._capability_view.set_snapshot(snapshot)

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("diag_col_name"), _t("diag_col_severity"),
            _t("diag_col_status"), _t("diag_col_detail"),
        ])

    def _refresh(self) -> None:
        if self._active_task is not None or self._view.closed:
            return
        self._view = _DiagnosticViewState(kind='running')
        self._table.setRowCount(0)
        self._render_summary()
        try:
            handle = self._task_controller.submit(partial(_diagnostic_work, run_diagnostics), owner=self)
        # pylint: disable-next=broad-exception-caught  # reason: restore UI state before preserving failed-start controls
        except BaseException as error:  # reason: display submit failures after preserving hard/cancel controls
            self._submission_failed(error)
            return
        self._active_task = handle
        handle.finished.connect(self._on_outcome)
        handle.progress.connect(self._on_progress)

    def _submission_failed(self, error: BaseException) -> None:
        self._view.kind = 'cancelled'
        self._render_summary()
        raise_caused_run_interruption(error)
        if not isinstance(error, Exception):
            raise error
        self._view.kind, self._view.error = 'error', scrub_secret_text(_ordinary_error_text(error))
        self._render_summary()

    def _stop(self) -> None:
        if self._active_task is not None:
            self._view.kind = 'stopping'
            self._active_task.cancel()
            self._render_summary()

    def _on_progress(self, progress: TaskProgress) -> None:
        if (self._active_task is None or progress.task_id != self._active_task.task_id
                or not self._view.accept_result or self._view.closed):
            return
        self._view.completed, self._view.total = progress.completed, progress.total or 0
        self._render_summary()

    def _on_outcome(self, outcome: TaskOutcome) -> None:
        if self._active_task is None or outcome.task_id != self._active_task.task_id:
            return
        self._active_task = None
        if not self._view.accept_result:
            self._view.kind = 'cancelled'
        elif outcome.status == 'cancelled':
            self._view.kind = 'cancelled'
        elif outcome.status == 'ok' and isinstance(outcome.value, DiagnosticsReport):
            self._view.kind, self._view.report = 'result', outcome.value
            self._fill_table(outcome.value)
        else:
            self._view.kind, self._view.error = 'error', outcome.error
        if not self._view.closed:
            self._render_summary()

    def _render_summary(self) -> None:
        report = self._view.report
        if self._view.kind == 'result' and report is not None:
            values = report.to_dict()
            key = 'diag_summary_ok' if report.ok else 'diag_summary_failed'
            text = _t(key).format(count=values['count'], failed=values['failed'])
        else:
            key = {'idle': 'diag_summary_idle', 'running': 'diag_summary_running',
                   'stopping': 'diag_summary_stopping', 'cancelled': 'diag_summary_cancelled',
                   'error': 'diag_summary_error', 'result': 'diag_summary_idle'}[self._view.kind]
            text = _t(key).format(error=self._view.error)
        self._summary_label.setText(text)
        progress = ''
        if self._active_task is not None and self._view.total:
            progress = _t('diag_progress').format(completed=self._view.completed, total=self._view.total)
        self._progress_label.setText(progress)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Abandon this run's display and request cleanup without blocking or closing another owner."""
        self._view.closed, self._view.accept_result = True, False
        if self._active_task is not None:
            self._view.kind = 'stopping'
            self._active_task.cancel()
        super().closeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        """Reopening never reaccepts a result from the run abandoned on close."""
        self._view.closed = False
        self._render_summary()
        super().showEvent(event)

    def _fill_table(self, report: DiagnosticsReport) -> None:
        self._table.setRowCount(len(report.checks))
        for row, check in enumerate(report.checks):
            cells = [
                check.name,
                check.severity,
                _t("diag_status_ok") if check.ok else _t("diag_status_fail"),
                check.detail,
            ]
            color = _SEVERITY_COLOR.get(check.severity)
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if color is not None and col == 1:
                    item.setForeground(QBrush(color))
                self._table.setItem(row, col, item)


__all__ = ["DiagnosticsTab"]
