"""Folder sync, the remote inbox and file transfer for the WebRTC viewer panel.

One interaction group of ``webrtc_panel._WebRTCViewerPanel``, kept as a mixin so the panel class
still owns every widget and slot under its original name.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Sequence


from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFileDialog, QMessageBox,
)

from je_auto_control.gui.remote_desktop._helpers import (
    _t,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.gui.remote_desktop.webrtc_panel_common import _PanelPart

if TYPE_CHECKING:  # imported lazily at runtime to keep startup cheap
    from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine


class _ViewerFilesMixin(_PanelPart):
    """Methods of ``_WebRTCViewerPanel``; the module docstring says which group."""

    # State this group owns; the panel's __init__ sets the starting values.
    _sync_engine: Optional[FolderSyncEngine]

    def _on_sync_browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, _t("rd_webrtc_sync_dir"),
        )
        if path:
            self._sync_dir_edit.setText(path)

    def _on_toggle_sync(self, checked: bool) -> None:
        if checked:
            if self._viewer is None or not self._viewer.authenticated:
                QMessageBox.information(
                    self, "WebRTC", _t("rd_webrtc_cad_not_connected"),
                )
                self._sync_btn.setChecked(False)
                return
            path = self._sync_dir_edit.text().strip()
            if not path:
                QMessageBox.warning(
                    self, "WebRTC", _t("rd_webrtc_sync_dir_required"),
                )
                self._sync_btn.setChecked(False)
                return
            from je_auto_control.utils.remote_desktop.file_sync import (
                FolderSyncEngine,
            )
            from pathlib import Path as _Path
            try:
                viewer = self._require_viewer()
                engine = FolderSyncEngine(
                    watch_dir=_Path(path),
                    sender=lambda local, name: viewer.send_file(
                        local, remote_name=name,
                    ),
                )
                self._sync_engine = engine
                engine.start()
            except (RuntimeError, OSError) as error:  # FileNotFoundError is an OSError
                QMessageBox.warning(self, "WebRTC", str(error))
                self._sync_btn.setChecked(False)
                return
            self._sync_btn.setText(_t("rd_webrtc_sync_stop"))
        else:
            if self._sync_engine is not None:
                try:
                    self._sync_engine.stop()
                except (RuntimeError, OSError):
                    pass
                self._sync_engine = None
            self._sync_btn.setText(_t("rd_webrtc_sync_start"))

    def _on_browse_refresh(self) -> None:
        if self._viewer is None or not self._viewer.authenticated:
            return
        try:
            self._viewer.request_inbox_listing()
        except (RuntimeError, OSError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_browse_pull_button(self) -> None:
        names = self._remote_files_table.selected_names()
        if not names:
            return
        self._on_pull_names(names)

    def _on_browse_delete_button(self) -> None:
        names = self._remote_files_table.selected_names()
        if not names:
            return
        self._on_delete_names(names)

    def _on_pull_names(self, names: Sequence[str]) -> None:
        if self._viewer is None or not self._viewer.authenticated:
            return
        try:
            for name in names:
                self._viewer.request_inbox_file(name)
        except (RuntimeError, OSError, ValueError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_delete_names(self, names: Sequence[str]) -> None:
        if not names or self._viewer is None or not self._viewer.authenticated:
            return
        confirm_text = (
            _t("rd_webrtc_browse_delete_confirm").format(name=names[0])
            if len(names) == 1
            else _t("rd_webrtc_browse_delete_many_confirm").format(n=len(names))
        )
        result = QMessageBox.question(
            self, "WebRTC", confirm_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            for name in names:
                self._viewer.delete_inbox_file(name)
        except (RuntimeError, OSError, ValueError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_upload_paths(self, paths: Sequence[str]) -> None:
        if self._viewer is None or not self._viewer.authenticated:
            QMessageBox.information(
                self, "WebRTC", _t("rd_webrtc_cad_not_connected"),
            )
            return
        sent = 0
        last_error = None
        for path in paths:
            try:
                self._viewer.send_file(path)
                sent += 1
            except (RuntimeError, OSError, ValueError) as error:
                last_error = error
                autocontrol_logger.warning("upload %s: %r", path, error)
        if sent:
            self._status_label.setText(
                _t("rd_webrtc_upload_done").format(n=sent),
            )
            QTimer.singleShot(500, self, self._on_browse_refresh)
        if last_error is not None and sent == 0:
            QMessageBox.warning(self, "WebRTC", str(last_error))

    def _on_copy_name(self, name: str) -> None:
        from PySide6.QtWidgets import QApplication as _QApp
        clipboard = _QApp.clipboard()
        if clipboard is not None:
            clipboard.setText(name)

    def _on_inbox_listing(self, files: object) -> None:
        from datetime import datetime
        if not isinstance(files, list):
            return
        def _format_mtime(value: Any) -> str:  # a field of the remote host's JSON listing
            try:
                return datetime.fromtimestamp(float(value)).strftime(
                    "%Y-%m-%d %H:%M:%S",
                )
            except (TypeError, ValueError, OSError, OverflowError):
                return str(value)
        self._remote_files_table.populate(files, _format_mtime)

    def _on_inbox_op_result(self, name: str, ok: bool, error: object) -> None:
        if ok:
            self._status_label.setText(
                _t("rd_webrtc_browse_op_ok").format(name=name),
            )
            # Refresh listing so the table reflects the change
            try:
                if self._viewer is not None and self._viewer.authenticated:
                    self._viewer.request_inbox_listing()
            except (RuntimeError, OSError):
                pass
        else:
            QMessageBox.warning(
                self, "WebRTC",
                _t("rd_webrtc_browse_op_failed").format(
                    name=name, error=str(error or ""),
                ),
            )

    def _on_send_file(self) -> None:
        if self._viewer is None or not self._viewer.authenticated:
            QMessageBox.information(
                self, "WebRTC", _t("rd_webrtc_cad_not_connected"),
            )
            return
        path, _filter = QFileDialog.getOpenFileName(
            self, _t("rd_webrtc_send_file"), "",
        )
        if not path:
            return
        try:
            self._viewer.send_file(path)
            self._status_label.setText(
                _t("rd_webrtc_file_sent").format(name=path),
            )
        except (RuntimeError, OSError, ValueError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_received_file(self, path: object) -> None:
        # Called from the asyncio thread, which has no Qt event loop:
        # QTimer.singleShot would never fire. Emit a signal — Qt queues the
        # status update onto the GUI thread.
        self._signals.file_received.emit(path)

    def _on_file_received_ui(self, path: object) -> None:
        self._status_label.setText(
            _t("rd_webrtc_file_received").format(name=str(path)),
        )


__all__ = ["_ViewerFilesMixin"]
