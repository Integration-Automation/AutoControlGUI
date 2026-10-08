"""Address book, known hosts, LAN browse and Wake-on-LAN for the WebRTC viewer panel.

One interaction group of ``webrtc_panel._WebRTCViewerPanel``, kept as a mixin so the panel class
still owns every widget and slot under its original name.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QFileDialog, QInputDialog, QMessageBox,
)

from je_auto_control.gui.remote_desktop._helpers import (
    _read_import_entries, _t,
)
from je_auto_control.gui.remote_desktop.webrtc_dialogs import (
    KnownHostsDialog, LanBrowseDialog,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import (
    send_magic_packet,
)
from je_auto_control.gui.remote_desktop.webrtc_panel_common import (
    _PanelPart,
    _JSON_FILE_FILTER,
)


class _ViewerAddressBookMixin(_PanelPart):
    """Methods of ``_WebRTCViewerPanel``; the module docstring says which group."""

    @staticmethod
    def _wol_defaults(entry: Optional[Dict[str, Any]]) -> tuple[str, str]:
        """Return (mac, broadcast) pre-fill values from a book entry."""
        if entry is None:
            return "", ""
        return (entry.get("mac_address", "") or "",
                entry.get("broadcast_address", "") or "")

    def _persist_wol_entry(self, entry: Optional[Dict[str, Any]], mac: str,
                           broadcast: str) -> None:
        """Save the MAC / broadcast just used back onto the book entry."""
        if entry is None:
            return
        self._address_book.upsert(
            host_id=entry.get("host_id", ""),
            server_url=entry.get("server_url", ""),
            mac_address=mac.strip(),
            broadcast_address=broadcast.strip() or None,
        )
        self._refresh_address_book()

    def _on_wake_on_lan(self) -> None:
        entry = self._address_list.selected_entry()
        mac, broadcast = self._wol_defaults(entry)
        mac, ok = QInputDialog.getText(
            self, _t("rd_webrtc_wake_on_lan"),
            _t("rd_webrtc_wol_mac_prompt"), text=mac,
        )
        if not ok or not mac.strip():
            return
        broadcast, ok2 = QInputDialog.getText(
            self, _t("rd_webrtc_wake_on_lan"),
            _t("rd_webrtc_wol_broadcast_prompt"),
            text=broadcast or "255.255.255.255",
        )
        if not ok2:
            return
        try:
            send_magic_packet(mac.strip(),
                              broadcast_address=broadcast.strip() or None)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))
            return
        self._persist_wol_entry(entry, mac, broadcast)
        QMessageBox.information(
            self, _t("rd_webrtc_wake_on_lan"), _t("rd_webrtc_wol_sent"),
        )

    def _on_ab_export(self) -> None:
        import json as _json
        path, _filter = QFileDialog.getSaveFileName(
            self, _t("rd_webrtc_ab_export"), "address_book.json",
            _JSON_FILE_FILTER,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                _json.dump({"entries": self._address_book.list_entries()},
                           fh, indent=2, ensure_ascii=False)
        except OSError as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_ab_import(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, _t("rd_webrtc_ab_import"), "", _JSON_FILE_FILTER,
        )
        if not path:
            return
        try:
            entries = _read_import_entries(path, "entries")
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))
            return
        added = 0
        for entry in entries:
            # Strings only: a numeric host_id was saved, then dropped on the
            # next load, and a numeric MAC reached Wake-on-LAN.
            text = {key: value for key, value in entry.items() if isinstance(value, str) and value}
            if not ("host_id" in text and "server_url" in text):
                continue
            try:
                self._address_book.upsert(
                    host_id=text["host_id"], server_url=text["server_url"],
                    label=text.get("label", ""),
                    mac_address=text.get("mac_address"),
                    broadcast_address=text.get("broadcast_address"),
                )
                added += 1
            except (ValueError, OSError) as error:
                autocontrol_logger.debug("ab import upsert: %r", error)
        QMessageBox.information(
            self, "WebRTC", _t("rd_webrtc_ab_import_done").format(n=added),
        )
        self._refresh_address_book()

    def _on_ab_clear(self) -> None:
        result = QMessageBox.question(
            self, "WebRTC", _t("rd_webrtc_ab_clear_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self._address_book.clear()
        self._refresh_address_book()

    def _on_manage_known_hosts(self) -> None:
        dialog = KnownHostsDialog(self._known_hosts, parent=self)
        dialog.exec()

    def _refresh_address_book(self) -> None:
        # Refresh tag filter combo
        current = self._tag_filter_combo.currentData() or ""
        self._tag_filter_combo.blockSignals(True)
        self._tag_filter_combo.clear()
        self._tag_filter_combo.addItem(_t("rd_webrtc_tag_all"), "")
        for tag in self._address_book.all_tags():
            self._tag_filter_combo.addItem(tag, tag)
        idx = self._tag_filter_combo.findData(current)
        if idx >= 0:
            self._tag_filter_combo.setCurrentIndex(idx)
        self._tag_filter_combo.blockSignals(False)
        # Apply filter
        active_tag = self._tag_filter_combo.currentData() or ""
        self._address_list.populate(
            self._address_book.list_entries(), tag_filter=active_tag,
        )

    def _on_address_tags(self, entry: Dict[str, Any]) -> None:
        existing = entry.get("tags", []) or []
        text, ok = QInputDialog.getText(
            self, _t("rd_webrtc_edit_tags"),
            _t("rd_webrtc_tags_prompt"),
            text=", ".join(existing),
        )
        if not ok:
            return
        new_tags = [t.strip() for t in text.split(",") if t.strip()]
        try:
            self._address_book.set_tags(
                host_id=entry.get("host_id", ""),
                server_url=entry.get("server_url", ""),
                tags=new_tags,
            )
        except (ValueError, OSError) as error:
            autocontrol_logger.debug("set_tags: %r", error)
        self._refresh_address_book()

    def _on_address_chosen(self, entry: Dict[str, Any]) -> None:
        self._server_edit.setText(entry.get("server_url", ""))
        self._host_id_edit.setText(entry.get("host_id", ""))
        self._on_connect_via_server()

    def _on_address_removed(self, entry: Dict[str, Any]) -> None:
        self._address_book.remove(
            host_id=entry.get("host_id", ""),
            server_url=entry.get("server_url", ""),
        )
        self._refresh_address_book()

    def _on_address_favorite(self, entry: Dict[str, Any]) -> None:
        try:
            self._address_book.toggle_favorite(
                host_id=entry.get("host_id", ""),
                server_url=entry.get("server_url", ""),
            )
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("toggle favorite: %r", error)
        self._refresh_address_book()

    def _on_connect_selected_address(self) -> None:
        entry = self._address_list.selected_entry()
        if entry is None:
            QMessageBox.information(
                self, "WebRTC", _t("rd_webrtc_no_address_selected"),
            )
            return
        self._on_address_chosen(entry)

    def _on_save_current_address(self) -> None:
        host_id = self._host_id_edit.text().strip()
        server_url = self._server_edit.text().strip()
        if not host_id or not server_url:
            QMessageBox.warning(
                self, "WebRTC", _t("rd_webrtc_save_address_missing_fields"),
            )
            return
        self._address_book.upsert(host_id=host_id, server_url=server_url)
        self._refresh_address_book()

    def _on_remove_selected_address(self) -> None:
        entry = self._address_list.selected_entry()
        if entry is not None:
            self._on_address_removed(entry)

    def _on_lan_browse(self) -> None:
        dialog = LanBrowseDialog(parent=self)
        dialog.chosen.connect(self._on_lan_chosen)
        dialog.exec()

    def _on_lan_chosen(self, svc: Dict[str, Any]) -> None:
        host_id = svc.get("host_id", "")
        signaling = svc.get("signaling_url", "")
        if host_id:
            self._host_id_edit.setText(host_id)
        if signaling:
            self._server_edit.setText(signaling)


__all__ = ["_ViewerAddressBookMixin"]
