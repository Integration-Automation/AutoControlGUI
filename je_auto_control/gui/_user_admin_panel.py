"""Thin local administration surface for the server's configured user store."""
from typing import Callable, List, Optional, Tuple

from PySide6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac.authorization import configured_user_store
from je_auto_control.utils.rbac.users import Role, UserAuthError, UserStore


class UserAdminPanel(TranslatableMixin, QGroupBox):
    """Manage the same in-process store used for REST and MCP authentication."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._tr(self, "admin_users_group")
        self.store: Optional[UserStore] = configured_user_store()
        self._identifier = QLineEdit()
        self._name = QLineEdit()
        self._role = QComboBox()
        self._role.addItems(Role.all())
        self._table = QTableWidget(0, 3)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout = QVBoxLayout(self)
        fields = QHBoxLayout()
        for key, widget in (("admin_user_id", self._identifier),
                            ("admin_user_name", self._name), ("admin_user_role", self._role)):
            fields.addWidget(self._tr(QLabel(), key))
            fields.addWidget(widget)
        layout.addLayout(fields)
        layout.addWidget(self._table)
        if self.store is None:
            layout.addWidget(self._tr(QLabel(), "admin_users_unconfigured"))
            self._identifier.setEnabled(False)
            self._name.setEnabled(False)
            self._role.setEnabled(False)
        self._refresh()

    def menu_actions(self) -> List[Tuple[str, Callable[[], None]]]:
        """Expose all mutations through the window's Actions menu."""
        return [("admin_users_refresh", self._refresh), ("admin_user_add", self._add),
                ("admin_user_remove", self._remove), ("admin_user_set_role", self._set_role),
                ("admin_user_rotate", self._rotate)]

    def _need_store(self) -> UserStore:
        if self.store is None:
            raise UserAuthError(language_wrapper.translate("admin_users_unconfigured"))
        return self.store

    def _refresh(self) -> None:
        records = self.store.list_users() if self.store else []
        self._table.setHorizontalHeaderLabels([
            language_wrapper.translate(key) for key in
            ("admin_user_id", "admin_user_name", "admin_user_role")])
        self._table.setRowCount(len(records))
        for row, record in enumerate(records):
            for column, value in enumerate((record.user_id, record.display_name, record.role)):
                self._table.setItem(row, column, QTableWidgetItem(value))

    def _run(self, operation: Callable[[], object]) -> None:
        try:
            operation()
            self._refresh()
        except (AutoControlException, ValueError, OSError) as error:
            QMessageBox.warning(self, self.title(), str(error))

    def _show_token(self, token: str) -> None:
        QMessageBox.information(self, self.title(),
                                language_wrapper.translate("admin_user_token_once") + "\n" + token)

    def _add(self) -> None:
        def operation() -> None:
            token = self._need_store().add_user(user_id=self._identifier.text().strip(),
                                               display_name=self._name.text().strip(),
                                               role=self._role.currentText())
            self._show_token(token)
        self._run(operation)

    def _remove(self) -> None:
        self._run(lambda: self._need_store().remove_user(self._identifier.text().strip()))

    def _set_role(self) -> None:
        self._run(lambda: self._need_store().set_role(self._identifier.text().strip(),
                                                    self._role.currentText()))

    def _rotate(self) -> None:
        self._run(lambda: self._show_token(
            self._need_store().rotate_token(self._identifier.text().strip())))
