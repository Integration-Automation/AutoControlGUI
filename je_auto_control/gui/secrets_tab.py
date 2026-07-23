"""Secrets tab: unlock the vault and manage ${secrets.NAME} entries."""
from typing import Optional

from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.secrets import (
    SecretStoreError, SecretStoreLocked, default_secret_manager,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class SecretsTab(TranslatableMixin, QWidget):
    """Manage the encrypted secret vault used by ``${secrets.NAME}``."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._status_label = QLabel()
        self._passphrase = QLineEdit()
        self._passphrase.setEchoMode(QLineEdit.Password)
        self._list = QListWidget()
        self._list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._build_layout()
        self._refresh_status()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._refresh_status()

    def _build_layout(self) -> None:
        # Vault commands (init/unlock/lock/add/remove/change passphrase)
        # run from the Actions menu; the tab keeps only passphrase input,
        # the entry list, and the status line.
        root = QVBoxLayout(self)
        unlock_box = self._tr(QGroupBox(), "secret_unlock_group")
        unlock_layout = QHBoxLayout(unlock_box)
        unlock_layout.addWidget(self._tr(QLabel(), "secret_passphrase_label"))
        self._passphrase.setPlaceholderText(_t("secret_passphrase_placeholder"))
        unlock_layout.addWidget(self._passphrase)
        root.addWidget(unlock_box)

        manage_box = self._tr(QGroupBox(), "secret_manage_group")
        manage_layout = QVBoxLayout(manage_box)
        manage_layout.addWidget(self._list)
        root.addWidget(manage_box, stretch=1)

        root.addWidget(self._status_label)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("secret_unlock", self._on_unlock),
            ("secret_lock", self._on_lock),
            ("secret_add", self._on_add),
            ("secret_remove", self._on_remove),
            ("secret_init", self._on_init),
            ("secret_change_passphrase", self._on_change_passphrase),
        ]

    def _refresh_status(self) -> None:
        manager = default_secret_manager
        if not manager.is_initialized:
            self._status_label.setText(_t("secret_status_uninitialized"))
        elif manager.is_unlocked:
            self._status_label.setText(_t("secret_status_unlocked"))
        else:
            self._status_label.setText(_t("secret_status_locked"))
        self._refresh_list()

    def _refresh_list(self) -> None:
        self._list.clear()
        if not default_secret_manager.is_unlocked:
            return
        try:
            names = default_secret_manager.list_names()
        except SecretStoreError:
            names = []
        for name in names:
            self._list.addItem(QListWidgetItem(name))

    def _consume_passphrase(self) -> str:
        text = self._passphrase.text()
        self._passphrase.clear()
        return text

    def _on_init(self) -> None:
        passphrase = self._consume_passphrase()
        if not passphrase:
            QMessageBox.warning(self, _t("secret_init"),
                                _t("secret_passphrase_required"))
            return
        try:
            default_secret_manager.initialize(passphrase)
        except SecretStoreError as error:
            QMessageBox.warning(self, _t("secret_init"), str(error))
            return
        QMessageBox.information(self, _t("secret_init"),
                                _t("secret_init_done"))
        self._refresh_status()

    def _on_unlock(self) -> None:
        passphrase = self._consume_passphrase()
        if not passphrase:
            return
        try:
            ok = default_secret_manager.unlock(passphrase)
        except SecretStoreError as error:
            QMessageBox.warning(self, _t("secret_unlock"), str(error))
            return
        if not ok:
            QMessageBox.warning(self, _t("secret_unlock"),
                                _t("secret_wrong_passphrase"))
        self._refresh_status()

    def _on_lock(self) -> None:
        default_secret_manager.lock()
        self._refresh_status()

    def _on_add(self) -> None:
        if not default_secret_manager.is_unlocked:
            QMessageBox.information(self, _t("secret_add"),
                                    _t("secret_unlock_first"))
            return
        name, ok = QInputDialog.getText(
            self, _t("secret_add"), _t("secret_name_prompt"),
        )
        if not ok or not name.strip():
            return
        value, ok = QInputDialog.getText(
            self, _t("secret_add"), _t("secret_value_prompt"),
            QLineEdit.Password,
        )
        if not ok:
            return
        try:
            default_secret_manager.set(name.strip(), value)
        except (SecretStoreError, SecretStoreLocked, ValueError) as error:
            QMessageBox.warning(self, _t("secret_add"), str(error))
            return
        self._refresh_list()

    def _on_remove(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        try:
            default_secret_manager.remove(item.text())
        except (SecretStoreError, SecretStoreLocked) as error:
            QMessageBox.warning(self, _t("secret_remove"), str(error))
            return
        self._refresh_list()

    def _on_change_passphrase(self) -> None:
        old, ok = QInputDialog.getText(
            self, _t("secret_change_passphrase"),
            _t("secret_old_passphrase_prompt"), QLineEdit.Password,
        )
        if not ok:
            return
        new, ok = QInputDialog.getText(
            self, _t("secret_change_passphrase"),
            _t("secret_new_passphrase_prompt"), QLineEdit.Password,
        )
        if not ok or not new:
            return
        try:
            default_secret_manager.change_passphrase(old, new)
        except (SecretStoreError, ValueError) as error:
            QMessageBox.warning(self, _t("secret_change_passphrase"),
                                str(error))
            return
        QMessageBox.information(
            self, _t("secret_change_passphrase"),
            _t("secret_change_done"),
        )
        self._refresh_status()
