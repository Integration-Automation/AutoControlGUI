"""Scheduler tab: register interval-based action JSON runs."""
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.scheduler import default_scheduler


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class SchedulerTab(TranslatableMixin, QWidget):
    """Add / remove / start / stop scheduler jobs."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._path_input = QLineEdit()
        self._interval_input = QLineEdit("60")
        self._repeat_check = self._tr(QCheckBox(), "sch_repeat")
        self._repeat_check.setChecked(True)
        self._table = QTableWidget(0, 5)
        self._apply_table_headers()
        self._running = False
        self._status = QLabel()
        self._apply_status()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh_table)
        self._build_layout()

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("sch_col_job_id"), _t("sch_col_script"),
            _t("sch_col_interval"), _t("sch_col_runs"),
            _t("sch_col_enabled"),
        ])

    def _apply_status(self) -> None:
        key = "sch_status_running" if self._running else "sch_status_stopped"
        self._status.setText(_t(key))

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_table_headers()
        self._apply_status()
        self._refresh_table()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        form = QHBoxLayout()
        form.addWidget(self._tr(QLabel(), "sch_script_label"))
        form.addWidget(self._path_input, stretch=1)
        browse = self._tr(QPushButton(), "browse")
        browse.clicked.connect(self._browse)
        form.addWidget(browse)
        form.addWidget(self._tr(QLabel(), "sch_interval_label"))
        form.addWidget(self._interval_input)
        form.addWidget(self._repeat_check)
        add_btn = self._tr(QPushButton(), "sch_add")
        add_btn.clicked.connect(self._on_add)
        form.addWidget(add_btn)
        root.addLayout(form)

        root.addWidget(self._table, stretch=1)

        ctl = QHBoxLayout()
        for key, handler in (
            ("sch_remove_selected", self._on_remove),
            ("sch_start", self._on_start),
            ("sch_stop", self._on_stop),
        ):
            btn = self._tr(QPushButton(), key)
            btn.clicked.connect(handler)
            ctl.addWidget(btn)
        ctl.addStretch()
        root.addLayout(ctl)
        root.addWidget(self._status)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("sch_dialog_select_script"), "", "JSON (*.json)",
        )
        if path:
            self._path_input.setText(path)

    def _on_add(self) -> None:
        path = self._path_input.text().strip()
        if not path:
            QMessageBox.warning(self, "Error", "Script path is required")
            return
        try:
            interval = float(self._interval_input.text() or "60")
        except ValueError:
            QMessageBox.warning(self, "Error", "Interval must be a number")
            return
        default_scheduler.add_job(
            script_path=path,
            interval_seconds=interval,
            repeat=self._repeat_check.isChecked(),
        )
        self._refresh_table()

    def _on_remove(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        job_id = self._table.item(row, 0).text()
        default_scheduler.remove_job(job_id)
        self._refresh_table()

    def _on_start(self) -> None:
        default_scheduler.start()
        self._timer.start()
        self._running = True
        self._apply_status()

    def _on_stop(self) -> None:
        default_scheduler.stop()
        self._timer.stop()
        self._running = False
        self._apply_status()

    def _refresh_table(self) -> None:
        jobs = default_scheduler.list_jobs()
        self._table.setRowCount(len(jobs))
        yes = _t("tr_yes")
        no = _t("tr_no")
        for row, job in enumerate(jobs):
            for col, value in enumerate((
                job.job_id, job.script_path, f"{job.interval_seconds:g}",
                str(job.runs), yes if job.enabled else no,
            )):
                self._table.setItem(row, col, QTableWidgetItem(value))
