"""Variables tab: inspect, seed, and clear the executor's runtime scope.

Runtime variables drive ``AC_set_var`` / ``AC_if_var`` / ``AC_for_each``
and live placeholder substitution. This tab is a thin Qt wrapper that
shows the current scope and lets users seed a JSON bag before running a
script that reads ``${var}`` placeholders.
"""
import json
from typing import Optional

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
    QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.executor.action_executor import executor


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class VariablesTab(TranslatableMixin, QWidget):
    """View and seed the global executor variable scope."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._table = QTableWidget(0, 2)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._table.verticalHeader().setVisible(False)
        self._set_name = QLineEdit()
        self._set_value = QLineEdit()
        self._seed_text = QTextEdit()
        self._status = QLabel()
        self._build_layout()
        self._apply_placeholders()
        self._refresh()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_placeholders()
        self._update_table_headers()

    def _apply_placeholders(self) -> None:
        self._set_name.setPlaceholderText(_t("vars_name_placeholder"))
        self._set_value.setPlaceholderText(_t("vars_value_placeholder"))
        self._seed_text.setPlaceholderText(_t("vars_seed_placeholder"))

    def _update_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("vars_col_name"), _t("vars_col_value"),
        ])

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)

        view_group = self._tr(QGroupBox(), "vars_current_group")
        view_layout = QVBoxLayout()
        self._update_table_headers()
        view_layout.addWidget(self._table)
        view_btns = QHBoxLayout()
        refresh_btn = self._tr(QPushButton(), "vars_refresh")
        refresh_btn.clicked.connect(self._refresh)
        clear_btn = self._tr(QPushButton(), "vars_clear")
        clear_btn.clicked.connect(self._on_clear)
        view_btns.addWidget(refresh_btn)
        view_btns.addWidget(clear_btn)
        view_btns.addStretch()
        view_layout.addLayout(view_btns)
        view_group.setLayout(view_layout)
        root.addWidget(view_group)

        set_group = self._tr(QGroupBox(), "vars_set_group")
        set_layout = QHBoxLayout()
        set_layout.addWidget(self._tr(QLabel(), "vars_name_label"))
        set_layout.addWidget(self._set_name, stretch=1)
        set_layout.addWidget(self._tr(QLabel(), "vars_value_label"))
        set_layout.addWidget(self._set_value, stretch=2)
        set_btn = self._tr(QPushButton(), "vars_set_btn")
        set_btn.clicked.connect(self._on_set_one)
        set_layout.addWidget(set_btn)
        set_group.setLayout(set_layout)
        root.addWidget(set_group)

        seed_group = self._tr(QGroupBox(), "vars_seed_group")
        seed_layout = QVBoxLayout()
        seed_layout.addWidget(self._seed_text)
        seed_btn = self._tr(QPushButton(), "vars_seed_btn")
        seed_btn.clicked.connect(self._on_seed_json)
        seed_layout.addWidget(seed_btn)
        seed_group.setLayout(seed_layout)
        root.addWidget(seed_group)

        root.addWidget(self._status)

    def _refresh(self) -> None:
        snapshot = executor.variables.as_dict()
        self._table.setRowCount(len(snapshot))
        for row, (name, value) in enumerate(sorted(snapshot.items())):
            self._table.setItem(row, 0, QTableWidgetItem(str(name)))
            display = self._format_value(value)
            self._table.setItem(row, 1, QTableWidgetItem(display))
        self._status.setText(
            _t("vars_count").replace("{n}", str(len(snapshot)))
        )

    @staticmethod
    def _format_value(value) -> str:
        if isinstance(value, (dict, list, tuple)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                return repr(value)
        return repr(value) if isinstance(value, str) else str(value)

    @staticmethod
    def _coerce_value(text: str):
        """Try JSON-decoding so '42' becomes int, fall back to raw string."""
        stripped = text.strip()
        if not stripped:
            return ""
        try:
            return json.loads(stripped)
        except (ValueError, TypeError):
            return text

    def _on_set_one(self) -> None:
        name = self._set_name.text().strip()
        if not name:
            self._status.setText(_t("vars_name_required"))
            return
        executor.variables.set(name, self._coerce_value(self._set_value.text()))
        self._set_name.clear()
        self._set_value.clear()
        self._refresh()

    def _on_clear(self) -> None:
        confirm = QMessageBox.question(
            self, _t("vars_clear"), _t("vars_clear_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        executor.variables.clear()
        self._refresh()

    def _on_seed_json(self) -> None:
        text = self._seed_text.toPlainText().strip()
        if not text:
            self._status.setText(_t("vars_seed_required"))
            return
        try:
            data = json.loads(text)
        except (ValueError, TypeError) as error:
            self._status.setText(f"{_t('vars_seed_invalid')}: {error}")
            return
        if not isinstance(data, dict):
            self._status.setText(_t("vars_seed_not_object"))
            return
        executor.variables.update_many(data)
        self._refresh()
