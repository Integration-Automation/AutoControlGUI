"""Trust list, audit log and file push for the WebRTC host panel.

One interaction group of ``webrtc_panel._WebRTCHostPanel``, kept as a mixin so the panel class
still owns every widget and slot under its original name.
"""
from __future__ import annotations


from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QMessageBox,
)

from je_auto_control.gui.remote_desktop._helpers import (
    _read_import_entries, _t,
)
from je_auto_control.gui.remote_desktop.webrtc_dialogs import (
    AuditLogDialog,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.gui.remote_desktop.webrtc_panel_common import (
    _JSON_FILE_FILTER,
)


class _HostTrustMixin:
    """Methods of ``_WebRTCHostPanel``; the module docstring says which group."""

    def _on_view_audit(self) -> None:
        from je_auto_control.utils.remote_desktop.audit_log import (
            default_audit_log,
        )
        AuditLogDialog(default_audit_log(), parent=self).exec()

    def _on_push_file(self) -> None:
        if self._multi_host is None or self._multi_host.session_count() == 0:
            QMessageBox.information(
                self, "WebRTC", _t("rd_webrtc_no_viewers"),
            )
            return
        path, _filter = QFileDialog.getOpenFileName(
            self, _t("rd_webrtc_push_file"), "",
        )
        if not path:
            return
        try:
            sent = self._multi_host.broadcast_file(path)
            QMessageBox.information(
                self, "WebRTC",
                _t("rd_webrtc_push_done").format(n=sent, name=path),
            )
        except (RuntimeError, OSError, ValueError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_export_trust(self) -> None:
        import json as _json
        path, _filter = QFileDialog.getSaveFileName(
            self, _t("rd_webrtc_trust_export"), "trusted_viewers.json",
            _JSON_FILE_FILTER,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                _json.dump({"viewers": self._trust_list.list_entries()},
                           fh, indent=2, ensure_ascii=False)
        except OSError as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_import_trust(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, _t("rd_webrtc_trust_import"), "", _JSON_FILE_FILTER,
        )
        if not path:
            return
        try:
            viewers = _read_import_entries(path, "viewers")
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))
            return
        added = 0
        for entry in viewers:
            vid, label = entry.get("viewer_id"), entry.get("label")
            if isinstance(vid, str) and vid:
                self._trust_list.add(vid, label=label if isinstance(label, str) else "")
                added += 1
        QMessageBox.information(
            self, "WebRTC",
            _t("rd_webrtc_trust_import_done").format(n=added),
        )
        self._refresh_trusted_list()

    def _refresh_trusted_list(self) -> None:
        self._trusted_list.populate(self._trust_list.list_entries())

    def _trust_session_viewer(self, sid: str) -> None:
        try:
            multi_host = self._require_multi_host()
            with multi_host._lock:
                host = multi_host._sessions.get(sid)
            full_vid = host.pending_viewer_id if host is not None else None
            if full_vid:
                self._trust_list.add(full_vid, label=f"sess {sid[:6]}")
                self._refresh_trusted_list()
        except (RuntimeError, OSError, ValueError) as error:
            autocontrol_logger.warning("trust viewer: %r", error)

    def _on_remove_trust(self, viewer_id: str) -> None:
        self._trust_list.remove(viewer_id)
        self._refresh_trusted_list()

    def _on_remove_trust_button(self) -> None:
        item = self._trusted_list.currentItem()
        if item is None:
            return
        viewer_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(viewer_id, str):
            self._on_remove_trust(viewer_id)

    def _on_clear_trust(self) -> None:
        result = QMessageBox.question(
            self, "WebRTC", _t("rd_webrtc_clear_trust_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self._trust_list.clear()
        self._refresh_trusted_list()


__all__ = ["_HostTrustMixin"]
