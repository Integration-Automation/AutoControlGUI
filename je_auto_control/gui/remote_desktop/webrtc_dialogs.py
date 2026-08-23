"""Custom dialogs / list widgets used by the WebRTC GUI panels.

Kept out of ``webrtc_panel.py`` so that file stays focused on layout
construction and signal wiring. The known-hosts browser lives in
``webrtc_known_hosts`` and is re-exported here, so callers keep importing
every dialog from one place.
"""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from je_auto_control.gui.remote_desktop._helpers import (
    _format_short_time, _iso_to_epoch, _t,
)
from je_auto_control.gui.remote_desktop.webrtc_known_hosts import (
    KnownHostsDialog,
)


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
            item = QListWidgetItem(self._format_entry(entry))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.addItem(item)

    @staticmethod
    def _format_entry(entry: dict) -> str:
        """Build the one-line display label for an address-book entry."""
        label = entry.get("label", "") or "(unnamed)"
        host_id = entry.get("host_id", "")
        star = "★ " if entry.get("favorite") else ""
        last_used = _format_short_time(entry.get("last_used"))
        tags = entry.get("tags", []) or []
        tag_str = (" [" + ", ".join(tags) + "]") if tags else ""
        suffix = f"  ({last_used})" if last_used else ""
        return f"{star}{label} - {host_id}{tag_str}{suffix}"

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
    # Emitted from the zeroconf thread; a queued connection marshals the
    # payload back onto the GUI thread (see _update_services).
    _services_changed = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._services_changed.connect(self._on_services_changed)
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
        self._browser: Optional[Any] = None
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
        # Called from the zeroconf browser thread, which has no Qt event loop:
        # QTimer.singleShot would create a timer with that thread's affinity and
        # never fire. Emit a signal instead — Qt queues it onto the GUI thread.
        self._services_changed.emit(dict(services))

    def _on_services_changed(self, services: dict) -> None:
        self._services = services
        self._refresh()

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
