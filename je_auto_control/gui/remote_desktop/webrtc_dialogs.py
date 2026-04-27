"""Custom dialogs / list widgets used by the WebRTC GUI panels.

Kept out of ``webrtc_panel.py`` so that file stays focused on layout
construction and signal wiring.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from je_auto_control.gui.remote_desktop._helpers import _t


class PendingViewerDialog(QDialog):
    """Three-button accept/reject prompt with an optional 'trust' choice.

    ``exec()`` returns one of :pyattr:`Rejected`, :pyattr:`AcceptOnce`,
    :pyattr:`AcceptAndTrust`.
    """

    Rejected = 0
    AcceptOnce = 1
    AcceptAndTrust = 2

    def __init__(self, viewer_id: Optional[str],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_t("rd_webrtc_pending_viewer_title"))
        self.setMinimumWidth(400)
        self._result = self.Rejected
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_t("rd_webrtc_pending_viewer_prompt")))
        if viewer_id:
            id_label = QLabel(f"viewer_id: {viewer_id[:12]}...{viewer_id[-4:]}")
            id_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse,
            )
            layout.addWidget(id_label)
        button_row = QHBoxLayout()
        reject = QPushButton(_t("rd_webrtc_reject"))
        reject.clicked.connect(self._on_reject)
        button_row.addWidget(reject)
        accept = QPushButton(_t("rd_webrtc_accept_once"))
        accept.clicked.connect(self._on_accept_once)
        button_row.addWidget(accept)
        trust = QPushButton(_t("rd_webrtc_accept_and_trust"))
        trust.clicked.connect(self._on_accept_and_trust)
        trust.setEnabled(bool(viewer_id))
        button_row.addWidget(trust)
        layout.addLayout(button_row)

    def _on_reject(self) -> None:
        self._result = self.Rejected
        self.accept()

    def _on_accept_once(self) -> None:
        self._result = self.AcceptOnce
        self.accept()

    def _on_accept_and_trust(self) -> None:
        self._result = self.AcceptAndTrust
        self.accept()

    def choice(self) -> int:
        return self._result


class TrustedViewersList(QListWidget):
    """List widget rendering trusted viewers; emits ``removed`` on Delete."""

    removed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(self.SelectionMode.SingleSelection)

    def populate(self, entries: list) -> None:
        self.clear()
        for entry in entries:
            viewer_id = entry.get("viewer_id", "")
            label = entry.get("label", "") or "(unlabeled)"
            last_used = _format_short_time(entry.get("last_used"))
            suffix = f"  ({last_used})" if last_used else ""
            display = f"{label} - {viewer_id[:8]}...{suffix}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, viewer_id)
            self.addItem(item)

    def keyPressEvent(self, event) -> None:  # noqa: N802 Qt override
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            item = self.currentItem()
            if item is not None:
                viewer_id = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(viewer_id, str):
                    self.removed.emit(viewer_id)
                    return
        super().keyPressEvent(event)


class AddressBookList(QListWidget):
    """List widget rendering address-book entries; emits selection signals."""

    chosen = Signal(dict)
    deleted = Signal(dict)
    favorite_toggled = Signal(dict)
    tags_edit_requested = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(self.SelectionMode.SingleSelection)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def _on_context_menu(self, position) -> None:
        entry = self.selected_entry()
        if entry is None:
            return
        menu = QMenu(self)
        connect_action = menu.addAction(_t("rd_webrtc_connect_selected"))
        fav_label = (
            "rd_webrtc_unfavorite" if entry.get("favorite")
            else "rd_webrtc_favorite"
        )
        fav_action = menu.addAction(_t(fav_label))
        tags_action = menu.addAction(_t("rd_webrtc_edit_tags"))
        delete_action = menu.addAction(_t("rd_webrtc_remove_selected"))
        chosen_act = menu.exec(self.viewport().mapToGlobal(position))
        if chosen_act is connect_action:
            self.chosen.emit(entry)
        elif chosen_act is fav_action:
            self.favorite_toggled.emit(entry)
        elif chosen_act is tags_action:
            self.tags_edit_requested.emit(entry)
        elif chosen_act is delete_action:
            self.deleted.emit(entry)

    def populate(self, entries: list, tag_filter: str = "") -> None:
        if tag_filter:
            entries = [
                e for e in entries
                if tag_filter in (e.get("tags", []) or [])
            ]
        # Favorites first, then by last_used desc
        sorted_entries = sorted(
            entries,
            key=lambda e: (
                not bool(e.get("favorite", False)),
                -_iso_to_epoch(e.get("last_used")),
            ),
        )
        self.clear()
        for entry in sorted_entries:
            label = entry.get("label", "") or "(unnamed)"
            host_id = entry.get("host_id", "")
            star = "★ " if entry.get("favorite") else ""
            last_used = _format_short_time(entry.get("last_used"))
            tags = entry.get("tags", []) or []
            tag_str = (" [" + ", ".join(tags) + "]") if tags else ""
            suffix = f"  ({last_used})" if last_used else ""
            display = f"{star}{label} - {host_id}{tag_str}{suffix}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.addItem(item)

    def selected_entry(self) -> Optional[dict]:
        item = self.currentItem()
        if item is None:
            return None
        entry = item.data(Qt.ItemDataRole.UserRole)
        return dict(entry) if isinstance(entry, dict) else None

    def _on_double_click(self, item) -> None:
        entry = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(entry, dict):
            self.chosen.emit(dict(entry))

    def keyPressEvent(self, event) -> None:  # noqa: N802 Qt override
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            entry = self.selected_entry()
            if entry is not None:
                self.deleted.emit(entry)
                return
        super().keyPressEvent(event)


class RemoteFilesTable(QTableWidget):
    """Multi-select remote-file table with drag-upload + context menu.

    Emits:
      * ``pull_requested(list[str])`` — names of selected rows
      * ``delete_requested(list[str])``
      * ``upload_requested(list[str])`` — local paths from a drag-drop
      * ``copy_name_requested(str)`` — single name from context menu
    """

    pull_requested = Signal(list)
    delete_requested = Signal(list)
    upload_requested = Signal(list)
    copy_name_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(0, 3, parent)
        self.setHorizontalHeaderLabels([
            _t("rd_webrtc_browse_col_name"),
            _t("rd_webrtc_browse_col_size"),
            _t("rd_webrtc_browse_col_mtime"),
        ])
        self.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch,
        )
        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection,
        )
        self.setMaximumHeight(180)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def selected_names(self) -> list:
        names = []
        for row in sorted({i.row() for i in self.selectedIndexes()}):
            item = self.item(row, 0)
            if item is not None:
                names.append(item.text())
        return names

    def populate(self, files: list, format_mtime) -> None:
        """Replace contents. ``format_mtime(value) -> str`` formats the column."""
        self.setRowCount(len(files))
        for row, entry in enumerate(files):
            name = str(entry.get("name", ""))
            size = int(entry.get("size", 0))
            mtime_str = format_mtime(entry.get("mtime"))
            self.setItem(row, 0, QTableWidgetItem(name))
            self.setItem(row, 1, QTableWidgetItem(f"{size:,}"))
            self.setItem(row, 2, QTableWidgetItem(mtime_str))

    # --- drag-and-drop ------------------------------------------------------

    def _accept_url_drag(self, event) -> None:
        """Shared drag handler: accept iff the payload carries file URLs."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragEnterEvent(self, event) -> None:  # noqa: N802 Qt override
        self._accept_url_drag(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802 Qt override
        self._accept_url_drag(event)

    def dropEvent(self, event) -> None:  # noqa: N802 Qt override
        urls = event.mimeData().urls()
        from pathlib import Path as _Path
        paths = [
            url.toLocalFile() for url in urls
            if url.isLocalFile() and url.toLocalFile()
        ]
        files = [p for p in paths if _Path(p).is_file()]
        if files:
            self.upload_requested.emit(files)
            event.acceptProposedAction()

    # --- context menu -------------------------------------------------------

    def _show_context_menu(self, position) -> None:
        names = self.selected_names()
        if not names:
            return
        menu = QMenu(self)
        pull_action = menu.addAction(_t("rd_webrtc_browse_pull"))
        delete_action = menu.addAction(_t("rd_webrtc_browse_delete"))
        copy_action = menu.addAction(_t("rd_webrtc_browse_copy_name"))
        if len(names) > 1:
            copy_action.setEnabled(False)
        chosen = menu.exec(self.viewport().mapToGlobal(position))
        if chosen is pull_action:
            self.pull_requested.emit(names)
        elif chosen is delete_action:
            self.delete_requested.emit(names)
        elif chosen is copy_action and names:
            self.copy_name_requested.emit(names[0])


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


def _short_fp(fp: Optional[str]) -> str:
    if not fp:
        return ""
    return fp[:16] + ("..." if len(fp) > 16 else "")


def _iso_to_epoch(value: Optional[str]) -> float:
    """Parse ISO; return Unix epoch (or 0 if invalid)."""
    if not value:
        return 0.0
    from datetime import datetime
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _format_short_time(value: Optional[str]) -> str:
    if not value:
        return ""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return ""
    return dt.astimezone().strftime("%m-%d %H:%M")


def _format_last_seen(value: Optional[str]) -> str:
    if not value:
        return ""
    # Stored as ISO 8601 (UTC); render as local-readable "YYYY-MM-DD HH:MM"
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


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


class AuditLogDialog(QDialog):
    """Browse the SQLite audit log with filter on event_type / host_id."""

    def __init__(self, audit_log, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._log = audit_log
        self.setWindowTitle(_t("rd_webrtc_audit_title"))
        self.setMinimumSize(820, 380)
        layout = QVBoxLayout(self)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(_t("rd_webrtc_audit_filter_type")))
        self._type_edit = QLineEdit()
        self._type_edit.setPlaceholderText(_t("rd_webrtc_audit_filter_type_ph"))
        filter_row.addWidget(self._type_edit)
        filter_row.addWidget(QLabel(_t("rd_webrtc_audit_filter_host")))
        self._host_edit = QLineEdit()
        filter_row.addWidget(self._host_edit)
        refresh_btn = QPushButton(_t("rd_webrtc_audit_refresh"))
        refresh_btn.clicked.connect(self._refresh)
        filter_row.addWidget(refresh_btn)
        layout.addLayout(filter_row)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels([
            _t("rd_webrtc_audit_col_ts"),
            _t("rd_webrtc_audit_col_type"),
            _t("rd_webrtc_audit_col_host"),
            _t("rd_webrtc_audit_col_viewer"),
            _t("rd_webrtc_audit_col_detail"),
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch,
        )
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers,
        )
        layout.addWidget(self._table)
        button_row = QHBoxLayout()
        button_row.addStretch()
        close_btn = QPushButton(_t("rd_webrtc_kh_close"))
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)
        self._refresh()

    def _refresh(self) -> None:
        from datetime import datetime
        rows = self._log.query(
            event_type=self._type_edit.text().strip() or None,
            host_id=self._host_edit.text().strip() or None,
            limit=500,
        )
        self._table.setRowCount(len(rows))
        for r, entry in enumerate(rows):
            ts = entry.get("ts", "")
            try:
                ts = datetime.fromisoformat(ts).astimezone().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except (TypeError, ValueError):
                pass
            cells = [
                ts,
                entry.get("event_type", ""),
                (entry.get("host_id") or "")[:16],
                (entry.get("viewer_id") or "")[:16],
                entry.get("detail") or "",
            ]
            for c, text in enumerate(cells):
                self._table.setItem(r, c, QTableWidgetItem(text))


class LanBrowseDialog(QDialog):
    """Dialog that browses the LAN for AutoControl hosts via mDNS.

    Polls a ``HostBrowser`` instance and lists discovered hosts in real
    time. ``chosen`` signal carries the selected service dict.
    """

    chosen = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_t("rd_webrtc_lan_title"))
        self.setMinimumSize(620, 260)
        self._services: dict = {}
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_t("rd_webrtc_lan_help")))
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels([
            _t("rd_webrtc_lan_col_host"),
            _t("rd_webrtc_lan_col_ip"),
            _t("rd_webrtc_lan_col_signaling"),
            _t("rd_webrtc_lan_col_name"),
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch,
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection,
        )
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers,
        )
        layout.addWidget(self._table)
        button_row = QHBoxLayout()
        button_row.addStretch()
        use_btn = QPushButton(_t("rd_webrtc_lan_use"))
        use_btn.clicked.connect(self._on_use)
        button_row.addWidget(use_btn)
        cancel_btn = QPushButton(_t("rd_webrtc_kh_close"))
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)
        # Defer browser start until the dialog is shown so we don't burn
        # mDNS sockets when the dialog is constructed lazily.
        self._browser = None
        self._start_browser()

    def _start_browser(self) -> None:
        try:
            from je_auto_control.utils.remote_desktop.lan_discovery import (
                HostBrowser, is_discovery_available,
            )
        except ImportError:
            return
        if not is_discovery_available():
            return
        try:
            self._browser = HostBrowser(on_change=self._update_services)
        except (RuntimeError, OSError):
            self._browser = None

    def _update_services(self, services: dict) -> None:
        # Called from zeroconf thread; marshal to GUI thread via signal-free
        # workaround: invokeMethod is overkill here, just store + post.
        self._services = dict(services)
        from PySide6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(0, self._refresh)

    def _refresh(self) -> None:
        items = sorted(self._services.values(), key=lambda s: s.get("host_id", ""))
        self._table.setRowCount(len(items))
        for r, svc in enumerate(items):
            self._table.setItem(r, 0, QTableWidgetItem(svc.get("host_id", "")))
            self._table.setItem(r, 1, QTableWidgetItem(svc.get("ip", "")))
            self._table.setItem(
                r, 2, QTableWidgetItem(svc.get("signaling_url", "")),
            )
            self._table.setItem(r, 3, QTableWidgetItem(svc.get("name", "")))

    def _on_use(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        host_id = self._table.item(row, 0).text() if self._table.item(row, 0) else ""
        if host_id and host_id in [s.get("host_id") for s in self._services.values()]:
            for svc in self._services.values():
                if svc.get("host_id") == host_id:
                    self.chosen.emit(svc)
                    self.accept()
                    return

    def closeEvent(self, event) -> None:  # noqa: N802 Qt override
        if self._browser is not None:
            try:
                self._browser.stop()
            except (RuntimeError, OSError):
                pass
            self._browser = None
        super().closeEvent(event)


__all__ = [
    "PendingViewerDialog", "TrustedViewersList", "AddressBookList",
    "RemoteFilesTable", "KnownHostsDialog", "AuditLogDialog",
    "LanBrowseDialog",
]
