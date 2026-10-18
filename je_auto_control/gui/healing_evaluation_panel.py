"""Fixed-frame version summaries, failure cases and provenance inside Self-Healing."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Callable, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFormLayout, QLabel, QLineEdit, QPlainTextEdit,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import WorkerHandle, start_worker
from je_auto_control.gui.healing_evaluation_worker import HealingEvaluationOutcome, HealingEvaluationWorker
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac.policy import authorize_command
from je_auto_control.utils.self_healing.evaluation import HealingComparison
from je_auto_control.utils.self_healing.evaluation_models import EvaluationRatio, HealingAttempt, HealingVersionReport
from je_auto_control.utils.self_healing.evaluation_io import write_healing_report

_SUMMARY = ("version", "accuracy", "false_positive", "recovery", "unknown", "p50", "p95")
_CASES = ("version", "sample", "correct", "run_id", "step_id")


def _t(key: str) -> str:
    return language_wrapper.translate("healing_eval_" + key)


def _table(columns: tuple[str, ...]) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    return table


def _populate(table: QTableWidget, rows: list[list[str]]) -> None:
    table.setRowCount(len(rows))
    for index, row in enumerate(rows):
        for column, value in enumerate(row):
            table.setItem(index, column, QTableWidgetItem(value))
    table.resizeColumnsToContents()


def _ratio(ratio: EvaluationRatio) -> str:
    return f"{ratio.numerator}/{ratio.denominator}" if ratio.denominator else _t("unknown")


def _version_row(name: str, version: HealingVersionReport) -> list[str]:
    ratios = [_ratio(ratio) for ratio in (version.accuracy, version.false_positive, version.recovery)]
    latency = [_t("unknown") if value is None else f"{value:.3f}" for value in (version.p50_ms, version.p95_ms)]
    return [name, *ratios, str(version.unknown), *latency]


def _case_row(row: HealingAttempt) -> list[str]:
    correct = _t("unknown") if row.correct is None else _t("correct_true" if row.correct else "correct_false")
    return [row.version, row.sample_id, correct, row.run_id or "", row.step_id or ""]


# pylint: disable-next=too-many-instance-attributes  # reason: owned view controls and one cancellable request
class HealingEvaluationPanel(TranslatableMixin, QWidget):
    """Run comparisons through Actions; show explicit populations and selected case details."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._generation = 0
        self._handle: Optional[WorkerHandle] = None
        self._worker: Optional[HealingEvaluationWorker] = None
        self._report: Optional[HealingComparison] = None
        self._path = QLineEdit()
        self._summary, self._cases = _table(_SUMMARY), _table(_CASES)
        self._details = QPlainTextEdit()
        self._details.setReadOnly(True)
        self._status = QLabel()
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        self._state, self._error = "idle", ""
        root = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow(self._tr(QLabel(), "healing_eval_path"), self._path)
        root.addLayout(form)
        root.addWidget(self._tr(QLabel(), "healing_eval_explanation"))
        views = QSplitter(Qt.Orientation.Vertical)
        views.addWidget(self._summary)
        cases = QSplitter(Qt.Orientation.Horizontal)
        cases.addWidget(self._cases)
        cases.addWidget(self._details)
        views.addWidget(cases)
        root.addWidget(views, stretch=1)
        root.addWidget(self._status)
        # pylint: disable-next=no-member  # reason: PySide binds the Qt signal at runtime
        self._path.textChanged.connect(self._path_changed)
        # pylint: disable-next=no-member  # reason: PySide binds the Qt signal at runtime
        self._cases.itemSelectionChanged.connect(self._show_case)
        self.retranslate()

    def menu_actions(self) -> list[tuple[str, Callable[[], None]]]:
        """Expose all operations through the owning tab's Actions menu."""
        return [("healing_eval_browse", self.browse), ("healing_eval_run", self.evaluate),
                ("healing_eval_cancel", self.cancel), ("healing_eval_export_json", self.export_json),
                ("healing_eval_export_html", self.export_html)]

    def retranslate(self) -> None:
        """Translate headers without discarding results or the active request."""
        TranslatableMixin.retranslate(self)
        self._summary.setHorizontalHeaderLabels([_t(key) for key in _SUMMARY])
        self._cases.setHorizontalHeaderLabels([_t(key) for key in _CASES])
        self._set_status(self._state, self._error)
        self._render()

    def _set_status(self, key: str, detail: str = "") -> None:
        self._state, self._error = key, detail
        self._status.setText(_t(key) + (": " + detail if detail else ""))

    def browse(self) -> None:
        """Choose a local manifest without running it."""
        path, _filter = QFileDialog.getOpenFileName(self, _t("browse"), "", "JSON (*.json)")
        if path:
            self._path.setText(path)

    def _path_changed(self, _text: str) -> None:
        self._generation += 1
        self.cancel()
        self._clear()
        self._set_status("idle")

    def _clear(self) -> None:
        self._report = None
        self._summary.setRowCount(0)
        self._cases.setRowCount(0)
        self._details.clear()

    def evaluate(self) -> None:
        """Start one background comparison after authorizing the owning caller."""
        if self._handle is not None:
            self._set_status("busy")
            return
        try:
            authorize_command("AC_self_heal_evaluate")
        except AutoControlException as error:
            self._set_status("error", str(error))
            return
        self._generation += 1
        self._clear()
        worker = HealingEvaluationWorker(self._generation, self._path.text().strip())
        self._worker = worker
        # pylint: disable-next=no-member  # reason: PySide binds the Qt signal at runtime
        self.destroyed.connect(worker.request_stop)
        self._set_status("running")
        self._handle = start_worker(self, worker, on_done=self._completed,
                                     on_thread_done=self._thread_done, on_fail=self._failed)

    @Slot()
    def cancel(self) -> None:
        """Request stop without blocking the GUI or publishing partial results."""
        if self._worker is not None:
            self._worker.request_stop()

    def _thread_done(self) -> None:
        self._handle = None
        self._worker = None

    def _failed(self, error: str) -> None:
        self._set_status("error", error)

    @Slot(object)
    def _completed(self, outcome: HealingEvaluationOutcome) -> None:
        if outcome.request_id != self._generation:
            return
        self._set_status(outcome.status, outcome.error)
        if outcome.report is not None:
            self._report = outcome.report
            self._render()

    def _render(self) -> None:
        if self._report is None:
            return
        _populate(self._summary, [_version_row(name, version) for name, version in self._report.versions.items()])
        _populate(self._cases, [_case_row(row) for row in self._report.attempts])

    def _show_case(self) -> None:
        if self._report is None or self._cases.currentRow() < 0:
            return
        attempt = self._report.attempts[self._cases.currentRow()]
        self._details.setPlainText(json.dumps(asdict(attempt), ensure_ascii=False, indent=2))

    def export_json(self) -> None:
        """Export the shared JSON snapshot chosen through a save dialog."""
        self._export("json")

    def export_html(self) -> None:
        """Export a standalone comparison with escaped case details."""
        self._export("html")

    def _export(self, suffix: str) -> None:
        if self._report is None:
            return
        path, _filter = QFileDialog.getSaveFileName(self, _t("export_" + suffix),
                                                   f"locator-comparison.{suffix}", f"*.{suffix}")
        if path:
            try:
                authorize_command("AC_self_heal_evaluate")
                write_healing_report(self._report, path)
            except (AutoControlException, OSError) as error:
                self._set_status("error", str(error))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802  # reason: Qt override name
        """Cancel cooperatively while worker ownership protects a closing panel."""
        self.cancel()
        super().closeEvent(event)
