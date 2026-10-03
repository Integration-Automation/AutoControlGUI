"""WebRTC viewer transfers controller; session and widget ownership stays on the panel."""
# pylint: disable=protected-access  # reason: typed controllers share their owning panel state

from __future__ import annotations

from typing import TYPE_CHECKING

# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtCore import QTimer

# pylint: enable=no-name-in-module
# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

# pylint: enable=no-name-in-module
from je_auto_control.gui.remote_desktop._helpers import _read_import_entries, _t
from je_auto_control.gui.remote_desktop.webrtc_common import _JSON_FILE_FILTER, stop_folder_sync
from je_auto_control.gui.remote_desktop.webrtc_dialogs import KnownHostsDialog, LanBrowseDialog
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import send_magic_packet

if TYPE_CHECKING:
    from je_auto_control.gui.remote_desktop.webrtc_viewer_panel import _WebRTCViewerPanel


class WebRTCViewerTransfersController:  # pylint: disable=too-few-public-methods  # reason: internal signal/slot controller
    """Viewer transfers interactions on a typed owned panel."""

    def __init__(self, panel: _WebRTCViewerPanel) -> None:
        self._panel = panel

    def _on_sync_browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self._panel, _t("rd_webrtc_sync_dir"))
        if path:
            self._panel._sync_dir_edit.setText(path)

    def _on_toggle_sync(self, checked: bool) -> None:
        if checked:
            if not self._ready_for_sync():
                self._panel._sync_btn.setChecked(False)
                return
            if self._panel._viewer is None or not self._panel._viewer.authenticated:
                QMessageBox.information(self._panel, "WebRTC", _t("rd_webrtc_cad_not_connected"))
                self._panel._sync_btn.setChecked(False)
                return
            path = self._panel._sync_dir_edit.text().strip()
            if not path:
                QMessageBox.warning(self._panel, "WebRTC", _t("rd_webrtc_sync_dir_required"))
                self._panel._sync_btn.setChecked(False)
                return
            # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
            from pathlib import (
                Path as _Path,
            )

            # pylint: enable=import-outside-toplevel
            # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
            from je_auto_control.utils.remote_desktop.file_sync import (
                FolderSyncEngine,
            )
            # pylint: enable=import-outside-toplevel

            try:
                viewer = self._panel._require_viewer()
                engine = FolderSyncEngine(
                    watch_dir=_Path(path), sender=lambda local, name: viewer.send_file(local, remote_name=name)
                )
                self._panel._sync_engine = engine
                engine.start()
            except (RuntimeError, OSError) as error:
                QMessageBox.warning(self._panel, "WebRTC", str(error))
                self._panel._sync_btn.setChecked(False)
                return
            self._panel._sync_btn.setText(_t("rd_webrtc_sync_stop"))
        else:
            stop_folder_sync(self._panel)
            self._panel._sync_btn.setText(_t("rd_webrtc_sync_start"))

    def _ready_for_sync(self) -> bool:
        engine = self._panel._sync_engine
        if engine is not None and engine.is_running():
            self._panel._sync_btn.setToolTip(_t('rd_webrtc_sync_draining'))
            return False
        self._panel._sync_engine = None
        self._panel._sync_btn.setToolTip('')
        return True

    def _on_browse_refresh(self) -> None:
        if self._panel._viewer is None or not self._panel._viewer.authenticated:
            return
        try:
            self._panel._viewer.request_inbox_listing()
        except (RuntimeError, OSError) as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))

    def _on_browse_pull_button(self) -> None:
        names = self._panel._remote_files_table.selected_names()
        if not names:
            return
        self._panel._on_pull_names(names)

    def _on_browse_delete_button(self) -> None:
        names = self._panel._remote_files_table.selected_names()
        if not names:
            return
        self._panel._on_delete_names(names)

    def _on_pull_names(self, names) -> None:
        if self._panel._viewer is None or not self._panel._viewer.authenticated:
            return
        try:
            for name in names:
                self._panel._viewer.request_inbox_file(name)
        except (RuntimeError, OSError, ValueError) as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))

    def _on_delete_names(self, names) -> None:
        if not names or self._panel._viewer is None or (not self._panel._viewer.authenticated):
            return
        confirm_text = (
            _t("rd_webrtc_browse_delete_confirm").format(name=names[0])
            if len(names) == 1
            else _t("rd_webrtc_browse_delete_many_confirm").format(n=len(names))
        )
        result = QMessageBox.question(
            self._panel, "WebRTC", confirm_text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            for name in names:
                self._panel._viewer.delete_inbox_file(name)
        except (RuntimeError, OSError, ValueError) as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))

    def _on_upload_paths(self, paths) -> None:
        if self._panel._viewer is None or not self._panel._viewer.authenticated:
            QMessageBox.information(self._panel, "WebRTC", _t("rd_webrtc_cad_not_connected"))
            return
        sent = 0
        last_error = None
        for path in paths:
            try:
                self._panel._viewer.send_file(path)
                sent += 1
            except (RuntimeError, OSError, ValueError) as error:
                last_error = error
                autocontrol_logger.warning("upload %s: %r", path, error)
        if sent:
            self._panel._status_label.setText(_t("rd_webrtc_upload_done").format(n=sent))
            QTimer.singleShot(500, self._panel, self._panel._on_browse_refresh)
        if last_error is not None and sent == 0:
            QMessageBox.warning(self._panel, "WebRTC", str(last_error))

    def _on_copy_name(self, name: str) -> None:
        # pylint: disable=no-name-in-module,import-outside-toplevel  # reason: lazy optional/cyclic boundary
        from PySide6.QtWidgets import (
            QApplication as _QApp,
        )
        # pylint: enable=no-name-in-module,import-outside-toplevel

        clipboard = _QApp.clipboard()
        if clipboard is not None:
            clipboard.setText(name)

    def _on_inbox_listing(self, files) -> None:
        # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
        from datetime import (
            datetime,
        )
        # pylint: enable=import-outside-toplevel

        if not isinstance(files, list):
            return

        def _format_mtime(value):
            try:
                return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError, OSError, OverflowError):
                return str(value)

        self._panel._remote_files_table.populate(files, _format_mtime)

    def _on_inbox_op_result(self, name: str, ok: bool, error) -> None:
        if ok:
            self._panel._status_label.setText(_t("rd_webrtc_browse_op_ok").format(name=name))
            try:
                if self._panel._viewer is not None and self._panel._viewer.authenticated:
                    self._panel._viewer.request_inbox_listing()
            except (RuntimeError, OSError):
                pass
        else:
            QMessageBox.warning(
                self._panel, "WebRTC", _t("rd_webrtc_browse_op_failed").format(name=name, error=str(error or ""))
            )

    def _on_send_file(self) -> None:
        if self._panel._viewer is None or not self._panel._viewer.authenticated:
            QMessageBox.information(self._panel, "WebRTC", _t("rd_webrtc_cad_not_connected"))
            return
        path, _filter = QFileDialog.getOpenFileName(self._panel, _t("rd_webrtc_send_file"), "")
        if not path:
            return
        try:
            self._panel._viewer.send_file(path)
            self._panel._status_label.setText(_t("rd_webrtc_file_sent").format(name=path))
        except (RuntimeError, OSError, ValueError) as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))

    @staticmethod
    def _wol_defaults(entry) -> tuple[str, str]:
        """Return (mac, broadcast) pre-fill values from a book entry."""
        if entry is None:
            return ("", "")
        return (entry.get("mac_address", "") or "", entry.get("broadcast_address", "") or "")

    def _persist_wol_entry(self, entry, mac: str, broadcast: str) -> None:
        """Save the MAC / broadcast just used back onto the book entry."""
        if entry is None:
            return
        self._panel._address_book.upsert(
            host_id=entry.get("host_id", ""),
            server_url=entry.get("server_url", ""),
            mac_address=mac.strip(),
            broadcast_address=broadcast.strip() or None,
        )
        self._panel._refresh_address_book()

    def _on_wake_on_lan(self) -> None:
        entry = self._panel._address_list.selected_entry()
        mac, broadcast = self._panel._wol_defaults(entry)
        mac, ok = QInputDialog.getText(
            self._panel, _t("rd_webrtc_wake_on_lan"), _t("rd_webrtc_wol_mac_prompt"), text=mac
        )
        if not ok or not mac.strip():
            return
        broadcast, ok2 = QInputDialog.getText(
            self._panel,
            _t("rd_webrtc_wake_on_lan"),
            _t("rd_webrtc_wol_broadcast_prompt"),
            text=broadcast or "255.255.255.255",
        )
        if not ok2:
            return
        try:
            send_magic_packet(mac.strip(), broadcast_address=broadcast.strip() or None)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))
            return
        self._panel._persist_wol_entry(entry, mac, broadcast)
        QMessageBox.information(self._panel, _t("rd_webrtc_wake_on_lan"), _t("rd_webrtc_wol_sent"))

    def _on_ab_export(self) -> None:
        # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
        import json as _json
        # pylint: enable=import-outside-toplevel

        path, _filter = QFileDialog.getSaveFileName(
            self._panel, _t("rd_webrtc_ab_export"), "address_book.json", _JSON_FILE_FILTER
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                _json.dump({"entries": self._panel._address_book.list_entries()}, fh, indent=2, ensure_ascii=False)
        except OSError as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))

    def _on_ab_import(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self._panel, _t("rd_webrtc_ab_import"), "", _JSON_FILE_FILTER)
        if not path:
            return
        try:
            entries = _read_import_entries(path, "entries")
        except (OSError, ValueError) as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))
            return
        added = 0
        for entry in entries:
            text = {key: value for key, value in entry.items() if isinstance(value, str) and value}
            if not ("host_id" in text and "server_url" in text):
                continue
            try:
                self._panel._address_book.upsert(
                    host_id=text["host_id"],
                    server_url=text["server_url"],
                    label=text.get("label", ""),
                    mac_address=text.get("mac_address"),
                    broadcast_address=text.get("broadcast_address"),
                )
                added += 1
            except (ValueError, OSError) as error:
                autocontrol_logger.debug("ab import upsert: %r", error)
        QMessageBox.information(self._panel, "WebRTC", _t("rd_webrtc_ab_import_done").format(n=added))
        self._panel._refresh_address_book()

    def _on_ab_clear(self) -> None:
        result = QMessageBox.question(
            self._panel,
            "WebRTC",
            _t("rd_webrtc_ab_clear_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self._panel._address_book.clear()
        self._panel._refresh_address_book()

    def _on_manage_known_hosts(self) -> None:
        dialog = KnownHostsDialog(self._panel._known_hosts, parent=self._panel)
        dialog.exec()

    def _refresh_address_book(self) -> None:
        current = self._panel._tag_filter_combo.currentData() or ""
        self._panel._tag_filter_combo.blockSignals(True)
        self._panel._tag_filter_combo.clear()
        self._panel._tag_filter_combo.addItem(_t("rd_webrtc_tag_all"), "")
        for tag in self._panel._address_book.all_tags():
            self._panel._tag_filter_combo.addItem(tag, tag)
        idx = self._panel._tag_filter_combo.findData(current)
        if idx >= 0:
            self._panel._tag_filter_combo.setCurrentIndex(idx)
        self._panel._tag_filter_combo.blockSignals(False)
        active_tag = self._panel._tag_filter_combo.currentData() or ""
        self._panel._address_list.populate(self._panel._address_book.list_entries(), tag_filter=active_tag)

    def _on_address_tags(self, entry: dict) -> None:
        existing = entry.get("tags", []) or []
        text, ok = QInputDialog.getText(
            self._panel, _t("rd_webrtc_edit_tags"), _t("rd_webrtc_tags_prompt"), text=", ".join(existing)
        )
        if not ok:
            return
        new_tags = [t.strip() for t in text.split(",") if t.strip()]
        try:
            self._panel._address_book.set_tags(
                host_id=entry.get("host_id", ""), server_url=entry.get("server_url", ""), tags=new_tags
            )
        except (ValueError, OSError) as error:
            autocontrol_logger.debug("set_tags: %r", error)
        self._panel._refresh_address_book()

    def _on_address_chosen(self, entry: dict) -> None:
        self._panel._server_edit.setText(entry.get("server_url", ""))
        self._panel._host_id_edit.setText(entry.get("host_id", ""))
        self._panel._on_connect_via_server()

    def _on_address_removed(self, entry: dict) -> None:
        self._panel._address_book.remove(host_id=entry.get("host_id", ""), server_url=entry.get("server_url", ""))
        self._panel._refresh_address_book()

    def _on_address_favorite(self, entry: dict) -> None:
        try:
            self._panel._address_book.toggle_favorite(
                host_id=entry.get("host_id", ""), server_url=entry.get("server_url", "")
            )
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("toggle favorite: %r", error)
        self._panel._refresh_address_book()

    def _on_connect_selected_address(self) -> None:
        entry = self._panel._address_list.selected_entry()
        if entry is None:
            QMessageBox.information(self._panel, "WebRTC", _t("rd_webrtc_no_address_selected"))
            return
        self._panel._on_address_chosen(entry)

    def _on_save_current_address(self) -> None:
        host_id = self._panel._host_id_edit.text().strip()
        server_url = self._panel._server_edit.text().strip()
        if not host_id or not server_url:
            QMessageBox.warning(self._panel, "WebRTC", _t("rd_webrtc_save_address_missing_fields"))
            return
        self._panel._address_book.upsert(host_id=host_id, server_url=server_url)
        self._panel._refresh_address_book()

    def _on_remove_selected_address(self) -> None:
        entry = self._panel._address_list.selected_entry()
        if entry is not None:
            self._panel._on_address_removed(entry)

    def _on_lan_browse(self) -> None:
        dialog = LanBrowseDialog(parent=self._panel)
        dialog.chosen.connect(self._panel._on_lan_chosen)
        dialog.exec()

    def _on_lan_chosen(self, svc: dict) -> None:
        host_id = svc.get("host_id", "")
        signaling = svc.get("signaling_url", "")
        if host_id:
            self._panel._host_id_edit.setText(host_id)
        if signaling:
            self._panel._server_edit.setText(signaling)

    def _on_file_received_ui(self, path) -> None:
        self._panel._status_label.setText(_t("rd_webrtc_file_received").format(name=str(path)))
