"""Presence Roster tab for the multi-viewer remote desktop.

Lists every viewer currently registered with
:class:`PresenceRegistry`, shows their role / cursor / last-seen
timestamp, and exposes one-click promote / demote / kick buttons. The
table auto-refreshes when the registry notifies of a change.
"""
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.remote_desktop.presence import (
    PresenceError, ROLE_CONTROLLER, ROLE_OBSERVER, ViewerPresence,
    default_presence_registry,
)


_COLUMNS = ("viewer_id", "label", "role", "cursor", "last_seen_iso")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class PresenceTab(TranslatableMixin, QWidget):
    """Roster view + role controls for the multi-viewer presence registry."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._registry = default_presence_registry()
        self._table = QTableWidget(0, len(_COLUMNS))
        self._status = QLabel()
        self._build_layout()
        # Listener fires on every change; the timer is a belt-and-braces
        # refresh in case a listener exception drops us off.
        self._registry.add_listener(self._on_registry_event)
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_translations()

    # --- layout ----------------------------------------------------

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        for key, slot in (
                ("presence_refresh_btn", self.refresh),
                ("presence_promote_btn", self._on_promote),
                ("presence_demote_btn", self._on_demote),
                ("presence_kick_btn", self._on_kick),
        ):
            btn = QPushButton()
            btn.setObjectName(key)
            btn.clicked.connect(slot)
            controls.addWidget(btn)
        controls.addStretch()
        root.addLayout(controls)
        root.addWidget(self._table, stretch=1)
        root.addWidget(self._status)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        self._apply_translations()

    def _apply_translations(self) -> None:
        for key in ("presence_refresh_btn", "presence_promote_btn",
                     "presence_demote_btn", "presence_kick_btn"):
            btn = self.findChild(QPushButton, key)
            if btn is not None:
                btn.setText(_t(key))
        self._table.setHorizontalHeaderLabels(
            [_t(f"presence_col_{col}") for col in _COLUMNS],
        )

    # --- actions ---------------------------------------------------

    def refresh(self) -> None:
        rows = self._registry.list()
        self._table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            self._populate_row(index, row)
        self._status.setText(
            _t("presence_count").replace("{count}", str(len(rows))),
        )

    def _populate_row(self, index: int, row: ViewerPresence) -> None:
        cursor = (f"({row.cursor_x}, {row.cursor_y})"
                  if row.cursor_x is not None and row.cursor_y is not None
                  else "")
        values = (row.viewer_id, row.label, row.role,
                  cursor, row.last_seen_iso)
        for col, text in enumerate(values):
            item = QTableWidgetItem(str(text))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self._table.setItem(index, col, item)

    def _on_registry_event(self, _viewer_id: str,
                            _row: Optional[ViewerPresence]) -> None:
        # Listener runs off the Qt thread; bounce onto the GUI loop.
        QTimer.singleShot(0, self.refresh)

    def _selected_viewer_id(self) -> Optional[str]:
        row = self._table.currentRow()
        if row < 0:
            self._status.setText(_t("presence_no_selection"))
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        return item.text()

    def _on_promote(self) -> None:
        self._update_selected_role(ROLE_CONTROLLER)

    def _on_demote(self) -> None:
        self._update_selected_role(ROLE_OBSERVER)

    def _update_selected_role(self, role: str) -> None:
        viewer_id = self._selected_viewer_id()
        if viewer_id is None:
            return
        try:
            self._registry.update_role(viewer_id, role)
        except PresenceError as error:
            self._status.setText(f"{_t('presence_error')}: {error}")
            return
        self.refresh()

    def _on_kick(self) -> None:
        viewer_id = self._selected_viewer_id()
        if viewer_id is None:
            return
        self._registry.unregister(viewer_id)
        self.refresh()


__all__ = ["PresenceTab"]
