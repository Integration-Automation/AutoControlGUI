"""RBAC users group of the REST API tab: list, add, re-role, rotate, remove.

A thin Qt surface over :mod:`je_auto_control.utils.rbac.admin` -- the same
functions ``AC_user_*`` and ``je_auto_control users`` call. The desktop user
is not an authenticated caller, so nothing is authorised here: whoever can
open this window can already edit the store file.

A token is shown once, in the "new token" field, right after ``add`` or
``rotate``; the next operation clears it. It is never written to a log.
"""
import os
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac import admin
from je_auto_control.utils.rbac.authorization import USERS_ENV
from je_auto_control.utils.rbac.users import Role, UserStore

_COLUMNS = ("rest_users_col_id", "rest_users_col_name", "rest_users_col_role")
_ERRORS = (AutoControlException, OSError, ValueError)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class RbacUsersPanel(TranslatableMixin, QGroupBox):
    """The user store behind the REST API: its path, its users, one-time tokens."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._tr(self, "rest_users_group", "setTitle")
        self._path_input = QLineEdit(os.environ.get(USERS_ENV, "").strip())
        self._path_input.setPlaceholderText(_t("rest_users_path_ph"))
        self._enable_check = QCheckBox()
        self._enable_check.setChecked(bool(self._path_input.text()))
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        self._id_input = QLineEdit()
        self._name_input = QLineEdit()
        self._role_input = QComboBox()
        self._role_input.addItems(Role.all())
        self._token_value = QLineEdit()
        self._token_value.setReadOnly(True)
        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._build_layout()
        self._retitle_columns()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        path_row = QHBoxLayout()
        path_row.addWidget(self._tr(QLabel(), "rest_users_path"))
        path_row.addWidget(self._path_input, stretch=1)
        root.addLayout(path_row)
        self._tr(self._enable_check, "rest_users_enable")
        root.addWidget(self._enable_check)
        root.addWidget(self._table)
        edit_row = QHBoxLayout()
        edit_row.addWidget(self._tr(QLabel(), "rest_users_id"))
        edit_row.addWidget(self._id_input, stretch=1)
        edit_row.addWidget(self._tr(QLabel(), "rest_users_name"))
        edit_row.addWidget(self._name_input, stretch=1)
        edit_row.addWidget(self._tr(QLabel(), "rest_users_role"))
        edit_row.addWidget(self._role_input)
        root.addLayout(edit_row)
        token_row = QHBoxLayout()
        token_row.addWidget(self._tr(QLabel(), "rest_users_new_token"))
        token_row.addWidget(self._token_value, stretch=1)
        root.addLayout(token_row)
        root.addWidget(self._status_label)

    def retranslate(self) -> None:
        """Re-apply the registered keys and the table's column titles."""
        super().retranslate()
        self._retitle_columns()

    def _retitle_columns(self) -> None:
        self._table.setHorizontalHeaderLabels([_t(key) for key in _COLUMNS])

    def menu_actions(self) -> List[Tuple[str, object]]:
        """The panel's commands, for the tab's Actions menu."""
        return [
            ("rest_users_refresh", self.refresh),
            ("rest_users_add", self._on_add),
            ("rest_users_set_role", self._on_set_role),
            ("rest_users_rotate", self._on_rotate),
            ("rest_users_remove", self._on_remove),
            ("rest_users_copy_token", self._on_copy_token),
        ]

    def users_path(self) -> Optional[str]:
        """The store path typed into the panel, or ``None`` when it is empty."""
        return self._path_input.text().strip() or None

    def user_store(self) -> Optional[UserStore]:
        """The store the REST server should authenticate against, when ticked."""
        path = self.users_path()
        if path is None or not self._enable_check.isChecked():
            return None
        return admin.management_store(path)

    def refresh(self) -> None:
        """Re-read the store and show its users; forgets a token still on show."""
        self._token_value.clear()
        self._reload()

    def _reload(self) -> bool:
        path = self.users_path()
        if path is None:
            self._table.setRowCount(0)
            self._status_label.setText(_t("rest_users_no_store"))
            return False
        try:
            users = admin.list_users(users_path=path)
        except _ERRORS as error:
            self._table.setRowCount(0)
            self._status_label.setText(str(error))
            return False
        self._table.setRowCount(len(users))
        for row, user in enumerate(users):
            for column, key in enumerate(("user_id", "display_name", "role")):
                self._table.setItem(row, column, QTableWidgetItem(str(user[key])))
        self._status_label.setText(
            _t("rest_users_count").format(count=len(users), path=path))
        return True

    def _on_row_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or self._table.item(row, 0) is None:
            return
        self._id_input.setText(self._table.item(row, 0).text())
        self._name_input.setText(self._table.item(row, 1).text())
        self._role_input.setCurrentText(self._table.item(row, 2).text())

    def _target(self) -> Optional[Tuple[str, str]]:
        """``(store path, user id)`` of the operation, or ``None`` with the reason shown."""
        self._token_value.clear()
        path = self.users_path()
        if path is None:
            self._status_label.setText(_t("rest_users_no_store"))
            return None
        user_id = self._id_input.text().strip()
        if not user_id:
            self._status_label.setText(_t("rest_users_no_user"))
            return None
        return path, user_id

    def _show_token(self, issued: dict) -> None:
        self._reload()
        self._token_value.setText(str(issued["token"]))
        self._status_label.setText(
            _t("rest_users_token_issued").format(user=issued["user_id"]))

    def _on_add(self) -> None:
        target = self._target()
        if target is None:
            return
        try:
            issued = admin.add_user(
                target[1], role=self._role_input.currentText(),
                display_name=self._name_input.text().strip(), users_path=target[0])
        except _ERRORS as error:
            self._status_label.setText(str(error))
            return
        self._show_token(issued)

    def _on_rotate(self) -> None:
        target = self._target()
        if target is None:
            return
        try:
            issued = admin.rotate_user_token(target[1], users_path=target[0])
        except _ERRORS as error:
            self._status_label.setText(str(error))
            return
        self._show_token(issued)

    def _on_set_role(self) -> None:
        target = self._target()
        if target is None:
            return
        try:
            admin.set_user_role(target[1], self._role_input.currentText(),
                                users_path=target[0])
        except _ERRORS as error:
            self._status_label.setText(str(error))
            return
        self._reload()

    def _on_remove(self) -> None:
        target = self._target()
        if target is None:
            return
        confirm = QMessageBox.question(
            self, _t("rest_users_remove"),
            _t("rest_users_remove_confirm").format(user=target[1]))
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            admin.remove_user(target[1], users_path=target[0])
        except _ERRORS as error:
            self._status_label.setText(str(error))
            return
        self._reload()

    def _on_copy_token(self) -> None:
        text = self._token_value.text()
        if text:
            QGuiApplication.clipboard().setText(text)


__all__ = ["RbacUsersPanel"]
