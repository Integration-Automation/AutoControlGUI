"""Test Suites tab: run a QA suite spec and manage flaky quarantine.

Thin wrapper over :func:`je_auto_control.run_suite`, the JUnit/Allure
report writers, and the quarantine store. Holds no business logic.
"""
import json
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
import je_auto_control as ac
from je_auto_control.utils.quarantine import (
    auto_quarantine_from_flakiness, default_quarantine_store,
)

_COLS = ("suite_col_case", "suite_col_status", "suite_col_time",
         "suite_col_message")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class TestSuiteTab(TranslatableMixin, QWidget):
    """Run suites, render scored cases, and manage the quarantine list."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._spec = QPlainTextEdit()
        self._spec.setPlaceholderText(
            '{"name": "Demo", "cases": [{"name": "c1", "actions": []}]}',
        )
        self._table = QTableWidget(0, len(_COLS))
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._summary = QLabel()
        self._quarantine = QListWidget()
        self._last_result = None
        self._apply_headers()
        self._build_layout()
        self._refresh_quarantine()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_headers()

    def _apply_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([_t(k) for k in _COLS])

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(QLabel(_t("suite_spec_label")))
        root.addWidget(self._spec, stretch=1)
        controls = QHBoxLayout()
        load_btn = self._tr(QPushButton(), "suite_load_file")
        load_btn.clicked.connect(self._on_load_file)
        run_btn = self._tr(QPushButton(), "suite_run")
        run_btn.clicked.connect(self._on_run)
        junit_btn = self._tr(QPushButton(), "suite_junit")
        junit_btn.clicked.connect(self._on_junit)
        allure_btn = self._tr(QPushButton(), "suite_allure")
        allure_btn.clicked.connect(self._on_allure)
        for btn in (load_btn, run_btn, junit_btn, allure_btn):
            controls.addWidget(btn)
        controls.addStretch()
        root.addLayout(controls)
        root.addWidget(self._table, stretch=2)
        root.addWidget(self._summary)
        root.addWidget(QLabel(_t("suite_q_label")))
        root.addWidget(self._quarantine)
        qrow = QHBoxLayout()
        auto_btn = self._tr(QPushButton(), "suite_q_auto")
        auto_btn.clicked.connect(self._on_auto_quarantine)
        remove_btn = self._tr(QPushButton(), "suite_q_remove")
        remove_btn.clicked.connect(self._on_release_selected)
        clear_btn = self._tr(QPushButton(), "suite_q_clear")
        clear_btn.clicked.connect(self._on_clear_quarantine)
        for btn in (auto_btn, remove_btn, clear_btn):
            qrow.addWidget(btn)
        qrow.addStretch()
        root.addLayout(qrow)

    def _parse_spec(self):
        return json.loads(self._spec.toPlainText() or "{}")

    def _on_load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, _t("suite_load_file"))
        if path:
            with open(path, encoding="utf-8") as handle:
                self._spec.setPlainText(handle.read())

    def _on_run(self) -> None:
        try:
            result = ac.run_suite(self._parse_spec())
        except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as err:
            self._summary.setText(_t("suite_error").replace("{error}", str(err)))
            return
        self._last_result = result
        self._render_result(result)

    def _render_result(self, result) -> None:
        self._table.setRowCount(len(result.cases))
        for row, case in enumerate(result.cases):
            values = (case.name, case.status, f"{case.duration_s:.3f}s",
                      case.message)
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, col, item)
        self._summary.setText(
            _t("suite_summary")
            .replace("{passed}", str(result.passed))
            .replace("{failed}", str(result.failed))
            .replace("{errored}", str(result.errored))
            .replace("{skipped}", str(result.skipped)),
        )

    def _on_junit(self) -> None:
        if self._last_result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, _t("suite_junit"),
                                              "junit.xml")
        if path:
            ac.write_junit_xml(self._last_result, path)

    def _on_allure(self) -> None:
        if self._last_result is None:
            return
        directory = QFileDialog.getExistingDirectory(self, _t("suite_allure"))
        if directory:
            ac.write_allure_results(self._last_result, directory)

    def _refresh_quarantine(self) -> None:
        self._quarantine.clear()
        for entry in default_quarantine_store().list():
            label = entry.name
            if entry.reason:
                label += f"  ({entry.reason})"
            self._quarantine.addItem(label)

    def _on_auto_quarantine(self) -> None:
        auto_quarantine_from_flakiness()
        self._refresh_quarantine()

    def _on_release_selected(self) -> None:
        item = self._quarantine.currentItem()
        if item is not None:
            default_quarantine_store().remove(item.text().split("  (")[0])
            self._refresh_quarantine()

    def _on_clear_quarantine(self) -> None:
        default_quarantine_store().clear()
        self._refresh_quarantine()
