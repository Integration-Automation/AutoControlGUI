"""Translate the existing folder toggle into owned start, reconnect handoff and explicit baseline reset."""
from __future__ import annotations

from typing import Any, Callable

# pylint: disable-next=no-name-in-module  # reason: Qt extension exports are supplied by its stubs
from PySide6.QtWidgets import QMessageBox

from je_auto_control.gui.remote_desktop._helpers import _t
from je_auto_control.gui.remote_desktop.folder_sync_io import FolderSyncHistory, bind_folder_receipts
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine


# pylint: disable=protected-access  # reason: this helper owns the extracted panel toggle lifecycle
def toggle_folder_sync(owner: Any, checked: bool, factory: Callable[..., FolderSyncEngine]) -> None:
    """Use the panel's existing affordance; reconnect retains metadata until the user explicitly starts again."""
    if checked:
        _start(owner, factory)
    else:
        if owner._sync_engine is not None:
            try:
                owner._sync_engine.stop()
            except (RuntimeError, OSError) as error:
                raise_caused_run_interruption(error)
                autocontrol_logger.warning('folder sync stop: %r', error)
            owner._sync_engine = None
        history = getattr(owner, '_sync_history', None)
        if history is not None:
            history.forget()
        owner._sync_btn.setText(_t('rd_webrtc_sync_start'))


def _start(owner: Any, factory: Callable[..., FolderSyncEngine]) -> None:
    if owner._viewer is None or not owner._viewer.authenticated:
        QMessageBox.information(owner, 'WebRTC', _t('rd_webrtc_cad_not_connected'))
        owner._sync_btn.setChecked(False)
        return
    path = owner._sync_dir_edit.text().strip()
    if not path:
        QMessageBox.warning(owner, 'WebRTC', _t('rd_webrtc_sync_dir_required'))
        owner._sync_btn.setChecked(False)
        return
    history = getattr(owner, '_sync_history', None)
    if history is None:
        history = owner._sync_history = FolderSyncHistory()
    engine = None
    try:
        viewer = owner._require_viewer()
        checkpoint = history.checkpoint(viewer, path)
        engine = factory(viewer, path, lambda: owner._viewer, lambda: owner._sync_engine, checkpoint)
        owner._sync_engine = engine
        bind_folder_receipts(viewer, lambda: owner._viewer, lambda: owner._sync_engine)
        engine.start()
        history.remember(viewer, path, engine)
    except (RuntimeError, OSError) as error:
        raise_caused_run_interruption(error)
        if engine is not None:
            engine.request_stop()
            owner._sync_engine = None
        QMessageBox.warning(owner, 'WebRTC', str(error))
        owner._sync_btn.setChecked(False)
        return
    owner._sync_btn.setText(_t('rd_webrtc_sync_stop'))
