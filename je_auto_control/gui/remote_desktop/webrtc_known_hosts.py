"""Known-hosts browser for the WebRTC GUI panels.

Split out of ``webrtc_dialogs.py``: the TOFU pin store gets its own table
dialog plus a small out-of-band pinning form, and neither shares state with
the viewer / address-book / audit dialogs next door. The shared fingerprint
and timestamp formatters live in ``_helpers``.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui.remote_desktop._helpers import (
    _format_last_seen, _short_fp, _t,
)


class KnownHostsDialog(QDialog):
    """Browse + forget the persistent KnownHosts (TOFU app + DTLS fingerprints)."""

    def __init__(self, known_hosts, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._known = known_hosts
        self.setWindowTitle(_t("rd_webrtc_known_hosts_title"))
        self.setMinimumSize(720, 360)
        layout = QVBoxLayout(self)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels([
            _t("rd_webrtc_kh_col_host"),
            _t("rd_webrtc_kh_col_app_fp"),
            _t("rd_webrtc_kh_col_dtls_fp"),
            _t("rd_webrtc_kh_col_last_seen"),
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch,
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch,
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection,
        )
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers,
        )
        layout.addWidget(self._table)
        button_row = QHBoxLayout()
        add_btn = QPushButton(_t("rd_webrtc_kh_add"))
        add_btn.clicked.connect(self._on_add_manual)
        button_row.addWidget(add_btn)
        import_btn = QPushButton(_t("rd_webrtc_kh_import"))
        import_btn.clicked.connect(self._on_import)
        button_row.addWidget(import_btn)
        export_btn = QPushButton(_t("rd_webrtc_kh_export"))
        export_btn.clicked.connect(self._on_export)
        button_row.addWidget(export_btn)
        copy_app_btn = QPushButton(_t("rd_webrtc_kh_copy_app"))
        copy_app_btn.clicked.connect(self._on_copy_app)
        button_row.addWidget(copy_app_btn)
        copy_dtls_btn = QPushButton(_t("rd_webrtc_kh_copy_dtls"))
        copy_dtls_btn.clicked.connect(self._on_copy_dtls)
        button_row.addWidget(copy_dtls_btn)
        forget_btn = QPushButton(_t("rd_webrtc_kh_forget"))
        forget_btn.clicked.connect(self._on_forget)
        button_row.addWidget(forget_btn)
        forget_stale_btn = QPushButton(_t("rd_webrtc_kh_forget_stale"))
        forget_stale_btn.clicked.connect(self._on_forget_stale)
        button_row.addWidget(forget_stale_btn)
        clear_btn = QPushButton(_t("rd_webrtc_kh_clear_all"))
        clear_btn.clicked.connect(self._on_clear_all)
        button_row.addWidget(clear_btn)
        button_row.addStretch()
        close_btn = QPushButton(_t("rd_webrtc_kh_close"))
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)
        self._refresh()

    def _refresh(self) -> None:
        from datetime import datetime, timedelta, timezone
        stale_after = timedelta(days=90)
        now = datetime.now(timezone.utc)
        stale_color = QColor("#888")
        entries = self._known.list_entries()
        self._table.setRowCount(len(entries))
        for row, (host_id, fps) in enumerate(sorted(entries.items())):
            self._populate_row(row, host_id, fps,
                               now=now, stale_after=stale_after,
                               stale_color=stale_color)

    def _populate_row(self, row: int, host_id: str, fps: dict, *,
                      now, stale_after, stale_color) -> None:
        items = [
            QTableWidgetItem(host_id),
            QTableWidgetItem(_short_fp(fps.get("app_fp"))),
            QTableWidgetItem(_short_fp(fps.get("dtls_fp"))),
            QTableWidgetItem(_format_last_seen(fps.get("last_seen"))),
        ]
        if self._is_stale(fps.get("last_seen"), now=now,
                          stale_after=stale_after):
            tip = _t("rd_webrtc_kh_stale_tip")
            for it in items:
                it.setForeground(stale_color)
                it.setToolTip(tip)
        for col, item in enumerate(items):
            self._table.setItem(row, col, item)

    @staticmethod
    def _is_stale(last_seen, *, now, stale_after) -> bool:
        if not last_seen:
            return False
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(last_seen)
        except (TypeError, ValueError):
            return False
        return now - dt > stale_after

    def _on_forget(self) -> None:
        rows = sorted(
            {i.row() for i in self._table.selectedIndexes()}, reverse=True,
        )
        if not rows:
            return
        for row in rows:
            item = self._table.item(row, 0)
            if item is None:
                continue
            self._known.forget(item.text())
        self._refresh()

    def _on_add_manual(self) -> None:
        dialog = _ManualKnownHostDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        host_id, app_fp, dtls_fp = dialog.values()
        if not host_id:
            return
        if app_fp:
            self._known.remember(host_id, app_fp)
        if dtls_fp:
            self._known.remember_dtls_fingerprint(host_id, dtls_fp)
        self._refresh()

    def _on_copy_app(self) -> None:
        self._copy_selected_fingerprint("app_fp")

    def _on_copy_dtls(self) -> None:
        self._copy_selected_fingerprint("dtls_fp")

    def _copy_selected_fingerprint(self, key: str) -> None:
        from PySide6.QtWidgets import QApplication as _QApp
        row = self._table.currentRow()
        if row < 0:
            return
        host_item = self._table.item(row, 0)
        if host_item is None:
            return
        entries = self._known.list_entries()
        fps = entries.get(host_item.text())
        if not fps:
            return
        value = fps.get(key) or ""
        clipboard = _QApp.clipboard()
        if clipboard is not None:
            clipboard.setText(value)

    def _on_export(self) -> None:
        import json
        path, _filter = QFileDialog.getSaveFileName(
            self, _t("rd_webrtc_kh_export"), "known_hosts.json",
            "JSON (*.json);;All (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._known.list_entries(), fh,
                          indent=2, ensure_ascii=False)
        except OSError as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_import(self) -> None:
        data = self._prompt_import_data()
        if data is None:
            return
        existing = self._known.list_entries()
        added = 0
        skipped = 0
        for host_id, value in data.items():
            outcome = self._import_one(host_id, value, existing)
            if outcome == "added":
                added += 1
            elif outcome == "skipped":
                skipped += 1
        QMessageBox.information(
            self, "WebRTC",
            _t("rd_webrtc_kh_import_done").format(added=added, skipped=skipped),
        )
        self._refresh()

    def _prompt_import_data(self):
        import json
        path, _filter = QFileDialog.getOpenFileName(
            self, _t("rd_webrtc_kh_import"), "", "JSON (*.json);;All (*)",
        )
        if not path:
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))
            return None
        if not isinstance(data, dict):
            QMessageBox.warning(
                self, "WebRTC", _t("rd_webrtc_kh_import_bad"),
            )
            return None
        return data

    def _import_one(self, host_id, value, existing) -> str:
        """Return ``"added"``, ``"skipped"``, or ``"ignored"`` per entry."""
        if not isinstance(host_id, str):
            return "ignored"
        app_fp, dtls_fp = self._extract_fingerprints(value)
        if app_fp is None and dtls_fp is None:
            return "ignored"
        if host_id in existing and not self._confirm_overwrite(host_id):
            return "skipped"
        if isinstance(app_fp, str) and app_fp:
            self._known.remember(host_id, app_fp)
        if isinstance(dtls_fp, str) and dtls_fp:
            self._known.remember_dtls_fingerprint(host_id, dtls_fp)
        return "added"

    @staticmethod
    def _extract_fingerprints(value):
        if isinstance(value, str):
            return value, None
        if isinstance(value, dict):
            return value.get("app_fp"), value.get("dtls_fp")
        return None, None

    def _confirm_overwrite(self, host_id: str) -> bool:
        result = QMessageBox.question(
            self, "WebRTC",
            _t("rd_webrtc_kh_import_overwrite").format(host=host_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def _on_forget_stale(self) -> None:
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        stale_ids = []
        for host_id, fps in self._known.list_entries().items():
            last_seen = fps.get("last_seen")
            if not last_seen:
                continue
            try:
                if datetime.fromisoformat(last_seen) < cutoff:
                    stale_ids.append(host_id)
            except (TypeError, ValueError):
                continue
        if not stale_ids:
            QMessageBox.information(
                self, "WebRTC", _t("rd_webrtc_kh_no_stale"),
            )
            return
        result = QMessageBox.question(
            self, "WebRTC",
            _t("rd_webrtc_kh_forget_stale_confirm").format(n=len(stale_ids)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        for host_id in stale_ids:
            self._known.forget(host_id)
        self._refresh()

    def _on_clear_all(self) -> None:
        from PySide6.QtWidgets import QMessageBox as _QMB
        result = _QMB.question(
            self, "WebRTC", _t("rd_webrtc_kh_clear_confirm"),
            _QMB.StandardButton.Yes | _QMB.StandardButton.No,
        )
        if result != _QMB.StandardButton.Yes:
            return
        for host_id in list(self._known.list_entries().keys()):  # NOSONAR python:S7504  # forget() mutates the underlying mapping — list() is required to avoid RuntimeError
            self._known.forget(host_id)
        self._refresh()




class _ManualKnownHostDialog(QDialog):
    """Tiny form dialog for pinning a host fingerprint out-of-band."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_t("rd_webrtc_kh_add"))
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText(_t("rd_webrtc_kh_add_host_ph"))
        self._app_edit = QLineEdit()
        self._app_edit.setPlaceholderText(_t("rd_webrtc_kh_add_app_ph"))
        self._dtls_edit = QLineEdit()
        self._dtls_edit.setPlaceholderText(_t("rd_webrtc_kh_add_dtls_ph"))
        form.addRow(_t("rd_webrtc_kh_col_host"), self._host_edit)
        form.addRow(_t("rd_webrtc_kh_col_app_fp"), self._app_edit)
        form.addRow(_t("rd_webrtc_kh_col_dtls_fp"), self._dtls_edit)
        layout.addLayout(form)
        button_row = QHBoxLayout()
        button_row.addStretch()
        ok = QPushButton(_t("rd_webrtc_kh_add"))
        ok.clicked.connect(self.accept)
        cancel = QPushButton(_t("rd_webrtc_kh_close"))
        cancel.clicked.connect(self.reject)
        button_row.addWidget(cancel)
        button_row.addWidget(ok)
        layout.addLayout(button_row)

    def values(self) -> tuple:
        return (
            self._host_edit.text().strip(),
            self._app_edit.text().strip(),
            self._dtls_edit.text().strip(),
        )
