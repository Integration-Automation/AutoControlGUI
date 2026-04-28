"""Email Triggers tab: bind IMAP mailboxes to action scripts."""
from typing import Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.triggers.email_trigger import (
    default_email_trigger_watcher,
)


_REFRESH_MS = 1500


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class EmailTriggersTab(TranslatableMixin, QWidget):
    """GUI front-end for :data:`default_email_trigger_watcher`."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("imap.example.com")
        self._port_input = QSpinBox()
        self._port_input.setRange(0, 65535)
        self._port_input.setValue(993)
        self._user_input = QLineEdit()
        self._user_input.setPlaceholderText("user@example.com")
        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.Password)
        self._password_input.setPlaceholderText(_t("eml_password_placeholder"))
        self._mailbox_input = QLineEdit("INBOX")
        self._search_input = QLineEdit("UNSEEN")
        self._poll_input = QSpinBox()
        self._poll_input.setRange(5, 86_400)
        self._poll_input.setValue(60)
        self._script_input = QLineEdit()
        self._ssl_check = self._tr(QCheckBox(), "eml_ssl")
        self._ssl_check.setChecked(True)
        self._mark_seen_check = self._tr(QCheckBox(), "eml_mark_seen")
        self._mark_seen_check.setChecked(True)
        self._status_label = QLabel()
        self._table = QTableWidget(0, 7)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive,
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._apply_table_headers()
        self._build_layout()
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_table_headers()
        self._refresh()

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("eml_col_id"), _t("eml_col_host"), _t("eml_col_user"),
            _t("eml_col_mailbox"), _t("eml_col_script"),
            _t("eml_col_fired"), _t("eml_col_error"),
        ])

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)

        engine_box = self._tr(QGroupBox(), "eml_engine_group")
        engine_layout = QHBoxLayout(engine_box)
        start_btn = self._tr(QPushButton(), "eml_start")
        start_btn.clicked.connect(self._on_start)
        engine_layout.addWidget(start_btn)
        stop_btn = self._tr(QPushButton(), "eml_stop")
        stop_btn.clicked.connect(self._on_stop)
        engine_layout.addWidget(stop_btn)
        poll_btn = self._tr(QPushButton(), "eml_poll_now")
        poll_btn.clicked.connect(self._on_poll_now)
        engine_layout.addWidget(poll_btn)
        engine_layout.addWidget(self._status_label)
        engine_layout.addStretch()
        root.addWidget(engine_box)

        add_box = self._tr(QGroupBox(), "eml_add_group")
        add_layout = QVBoxLayout(add_box)
        host_row = QHBoxLayout()
        host_row.addWidget(self._tr(QLabel(), "eml_host_label"))
        host_row.addWidget(self._host_input)
        host_row.addWidget(self._tr(QLabel(), "eml_port_label"))
        host_row.addWidget(self._port_input)
        host_row.addWidget(self._ssl_check)
        add_layout.addLayout(host_row)
        creds_row = QHBoxLayout()
        creds_row.addWidget(self._tr(QLabel(), "eml_user_label"))
        creds_row.addWidget(self._user_input)
        creds_row.addWidget(self._tr(QLabel(), "eml_password_label"))
        creds_row.addWidget(self._password_input)
        add_layout.addLayout(creds_row)
        mb_row = QHBoxLayout()
        mb_row.addWidget(self._tr(QLabel(), "eml_mailbox_label"))
        mb_row.addWidget(self._mailbox_input)
        mb_row.addWidget(self._tr(QLabel(), "eml_search_label"))
        mb_row.addWidget(self._search_input)
        add_layout.addLayout(mb_row)
        poll_row = QHBoxLayout()
        poll_row.addWidget(self._tr(QLabel(), "eml_poll_label"))
        poll_row.addWidget(self._poll_input)
        poll_row.addWidget(self._mark_seen_check)
        poll_row.addStretch()
        add_layout.addLayout(poll_row)
        script_row = QHBoxLayout()
        script_row.addWidget(self._tr(QLabel(), "eml_script_label"))
        script_row.addWidget(self._script_input)
        browse_btn = self._tr(QPushButton(), "eml_browse")
        browse_btn.clicked.connect(self._on_browse)
        script_row.addWidget(browse_btn)
        register_btn = self._tr(QPushButton(), "eml_register")
        register_btn.clicked.connect(self._on_register)
        script_row.addWidget(register_btn)
        add_layout.addLayout(script_row)
        root.addWidget(add_box)

        root.addWidget(self._table, stretch=1)
        action_row = QHBoxLayout()
        remove_btn = self._tr(QPushButton(), "eml_remove")
        remove_btn.clicked.connect(self._on_remove)
        action_row.addWidget(remove_btn)
        action_row.addStretch()
        root.addLayout(action_row)

    def _on_start(self) -> None:
        default_email_trigger_watcher.start()
        self._refresh()

    def _on_stop(self) -> None:
        default_email_trigger_watcher.stop()
        self._refresh()

    def _on_poll_now(self) -> None:
        try:
            fired = default_email_trigger_watcher.poll_once()
        except (OSError, RuntimeError) as error:
            QMessageBox.warning(self, _t("eml_poll_now"), str(error))
            return
        QMessageBox.information(
            self, _t("eml_poll_now"),
            _t("eml_poll_done").replace("{n}", str(fired)),
        )
        self._refresh()

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("eml_browse"), "", "JSON (*.json)",
        )
        if path:
            self._script_input.setText(path)

    def _on_register(self) -> None:
        host = self._host_input.text().strip()
        user = self._user_input.text().strip()
        password = self._password_input.text()
        script = self._script_input.text().strip()
        if not host or not user or not password or not script:
            QMessageBox.warning(self, _t("eml_register"),
                                _t("eml_required_fields"))
            return
        try:
            default_email_trigger_watcher.add(
                host=host, username=user, password=password,
                script_path=script,
                port=int(self._port_input.value()),
                use_ssl=self._ssl_check.isChecked(),
                mailbox=self._mailbox_input.text().strip() or "INBOX",
                search_criteria=self._search_input.text().strip() or "UNSEEN",
                mark_seen=self._mark_seen_check.isChecked(),
                poll_seconds=float(self._poll_input.value()),
            )
        except ValueError as error:
            QMessageBox.warning(self, _t("eml_register"), str(error))
            return
        self._password_input.clear()
        self._refresh()

    def _on_remove(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        default_email_trigger_watcher.remove(item.text())
        self._refresh()

    def _refresh(self) -> None:
        running = default_email_trigger_watcher.is_running
        self._status_label.setText(
            _t("eml_running") if running else _t("eml_stopped"),
        )
        rows = default_email_trigger_watcher.list_triggers()
        self._table.setRowCount(len(rows))
        for row, trigger in enumerate(rows):
            values = (
                trigger.trigger_id,
                f"{trigger.host}:{trigger.port}",
                trigger.username,
                trigger.mailbox,
                trigger.script_path,
                str(trigger.fired),
                trigger.last_error or "",
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, col, item)
