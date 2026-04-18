"""Scheduler tab: register interval-based action JSON runs."""
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.utils.scheduler import default_scheduler


class SchedulerTab(QWidget):
    """Add / remove / start / stop scheduler jobs."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._path_input = QLineEdit()
        self._interval_input = QLineEdit("60")
        self._repeat_check = QCheckBox("Repeat")
        self._repeat_check.setChecked(True)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Job ID", "Script", "Interval (s)", "Runs", "Enabled"]
        )
        self._status = QLabel("Scheduler stopped")
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh_table)
        self._build_layout()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        form = QHBoxLayout()
        form.addWidget(QLabel("Script:"))
        form.addWidget(self._path_input, stretch=1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        form.addWidget(browse)
        form.addWidget(QLabel("Every (s):"))
        form.addWidget(self._interval_input)
        form.addWidget(self._repeat_check)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._on_add)
        form.addWidget(add_btn)
        root.addLayout(form)

        root.addWidget(self._table, stretch=1)

        ctl = QHBoxLayout()
        for label, handler in (
            ("Remove selected", self._on_remove),
            ("Start scheduler", self._on_start),
            ("Stop scheduler", self._on_stop),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            ctl.addWidget(btn)
        ctl.addStretch()
        root.addLayout(ctl)
        root.addWidget(self._status)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select script", "", "JSON (*.json)")
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
        self._status.setText("Scheduler running")

    def _on_stop(self) -> None:
        default_scheduler.stop()
        self._timer.stop()
        self._status.setText("Scheduler stopped")

    def _refresh_table(self) -> None:
        jobs = default_scheduler.list_jobs()
        self._table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            for col, value in enumerate((
                job.job_id, job.script_path, f"{job.interval_seconds:g}",
                str(job.runs), "Yes" if job.enabled else "No",
            )):
                self._table.setItem(row, col, QTableWidgetItem(value))
