"""Host-side ACL prompt dialog for USB passthrough.

When a viewer requests OPEN of a device whose ACL rule has
``prompt_on_open = True``, the host operator gets a modal dialog
showing what's being asked and chooses Allow / Deny. A "Remember
this decision" checkbox persists the verdict back to the ACL so
future opens of the same device skip the prompt.

The prompt callback wired into :class:`UsbPassthroughSession` is
synchronous — it must return ``True`` / ``False`` from a non-GUI
thread (the callback runs on the WebRTC/asyncio bridge thread, not
the Qt main thread). :class:`PromptBridge` does the cross-thread
marshalling: the worker thread calls ``decide()``, which posts a
``QMetaObject.invokeMethod`` to the GUI thread, waits on a
``threading.Event``, and returns the operator's verdict.
"""
from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QMetaObject, QObject, Q_ARG, Qt, Slot
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.usb.passthrough.acl import AclRule, UsbAcl


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class UsbPassthroughPromptDialog(TranslatableMixin, QDialog):
    """Modal dialog asking the host operator to allow / deny one OPEN."""

    def __init__(self, *, vendor_id: str, product_id: str,
                 serial: Optional[str], viewer_id: Optional[str],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._tr(self, "usb_prompt_title", setter="setWindowTitle")
        self._vendor_id = vendor_id
        self._product_id = product_id
        self._serial = serial
        self._viewer_id = viewer_id
        self._remember_check = QCheckBox()
        self._tr(self._remember_check, "usb_prompt_remember")
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes
            | QDialogButtonBox.StandardButton.No,
        )
        self._buttons.button(
            QDialogButtonBox.StandardButton.Yes,
        ).setText(_t("usb_prompt_allow"))
        self._buttons.button(
            QDialogButtonBox.StandardButton.No,
        ).setText(_t("usb_prompt_deny"))
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._build_layout()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        intro = self._tr(QLabel(), "usb_prompt_intro")
        intro.setWordWrap(True)
        root.addWidget(intro)
        form = QFormLayout()
        form.addRow(self._tr(QLabel(), "usb_prompt_vendor"),
                    QLabel(self._vendor_id))
        form.addRow(self._tr(QLabel(), "usb_prompt_product"),
                    QLabel(self._product_id))
        form.addRow(self._tr(QLabel(), "usb_prompt_serial"),
                    QLabel(self._serial or "—"))
        form.addRow(self._tr(QLabel(), "usb_prompt_viewer"),
                    QLabel(self._viewer_id or "—"))
        root.addLayout(form)
        root.addWidget(self._remember_check)
        root.addWidget(self._buttons)

    @property
    def remember(self) -> bool:
        return self._remember_check.isChecked()


class PromptBridge(QObject):
    """Thread-safe bridge from worker → GUI → worker for one decision.

    Worker thread calls :meth:`decide` (blocking). The bridge posts a
    queued slot invocation onto the Qt thread, opens the dialog,
    captures the verdict, optionally writes back to the ACL, and
    signals the worker via a ``threading.Event``.
    """

    def __init__(self, *, acl: Optional[UsbAcl] = None,
                 dialog_parent: Optional[QWidget] = None) -> None:
        super().__init__(dialog_parent)
        self._acl = acl
        self._dialog_parent = dialog_parent

    def decide(self, vendor_id: str, product_id: str,
               serial: Optional[str],
               *, viewer_id: Optional[str] = None,
               wait_timeout_s: float = 60.0) -> bool:
        """Worker-thread entry point. Blocks on the operator's choice."""
        result: dict = {"allow": False, "remember": False}
        done = threading.Event()
        QMetaObject.invokeMethod(
            self, "_show_dialog",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, vendor_id),
            Q_ARG(str, product_id),
            Q_ARG(str, serial or ""),
            Q_ARG(str, viewer_id or ""),
            Q_ARG(object, result),
            Q_ARG(object, done),
        )
        if not done.wait(timeout=wait_timeout_s):
            return False
        # Sonar can't see through the cross-thread QMetaObject
        # .invokeMethod + queued slot above: ``result`` is mutated by
        # ``_show_dialog`` on the GUI thread before ``done`` is set,
        # so neither key is guaranteed False at this point.
        if result["allow"] and result["remember"] and self._acl is not None:  # NOSONAR — cross-thread mutation through Q_ARG(object, result), see comment above
            self._acl.add_rule(AclRule(
                vendor_id=vendor_id, product_id=product_id,
                serial=(serial or None),
                label=f"prompt-approved {vendor_id}:{product_id}",
                allow=True, prompt_on_open=False,
            ))
        return bool(result["allow"])

    @Slot(str, str, str, str, object, object)
    def _show_dialog(self, vendor_id: str, product_id: str,
                     serial: str, viewer_id: str,
                     result: dict, done: threading.Event) -> None:
        dialog = UsbPassthroughPromptDialog(
            vendor_id=vendor_id, product_id=product_id,
            serial=serial or None, viewer_id=viewer_id or None,
            parent=self._dialog_parent,
        )
        try:
            outcome = dialog.exec()
            result["allow"] = outcome == QDialog.DialogCode.Accepted
            result["remember"] = dialog.remember
        finally:
            done.set()


def attach_prompt_to_session(session, *,
                             acl: Optional[UsbAcl] = None,
                             dialog_parent: Optional[QWidget] = None,
                             ) -> PromptBridge:
    """Convenience wire-up: install a Qt-driven prompt callback on the session.

    Returns the :class:`PromptBridge` so the caller can keep a reference
    (Qt parent ownership otherwise garbage-collects it). Requires a
    running ``QApplication`` in the GUI thread.
    """
    if QApplication.instance() is None:
        raise RuntimeError(
            "attach_prompt_to_session requires a running QApplication",
        )
    bridge = PromptBridge(acl=acl, dialog_parent=dialog_parent)
    session._prompt_callback = bridge.decide  # type: ignore[attr-defined]
    return bridge


__all__ = [
    "PromptBridge", "UsbPassthroughPromptDialog",
    "attach_prompt_to_session",
]
