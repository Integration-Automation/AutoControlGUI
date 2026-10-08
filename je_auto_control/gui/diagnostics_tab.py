"""System diagnostics tab: subsystem checks, and what this session can do.

Two tables. The first is the battery of subsystem checks. The second is the
capability snapshot from :func:`probe_capabilities` — input, capture,
recording and the stop key, each with its state and, where something stands
in the way, what to do about it. Both are read-only views of headless data:
the same snapshot is what ``AC_probe_capabilities`` and the MCP tool return.
"""
from typing import List, Optional

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.linux_wayland._select_input import (
    close_input_session, reset_input_authorisation,
)
from je_auto_control.utils.diagnostics.diagnostics import run_diagnostics
from je_auto_control.wrapper.capabilities import (
    Capability, CapabilityStatus, probe_capabilities,
)


_SEVERITY_COLOR = {
    "info": QColor("#1e8a3a"),
    "warn": QColor("#b08400"),
    "error": QColor("#c0392b"),
}

#: Capability states by how much attention they want.
_STATE_SEVERITY = {
    CapabilityStatus.AVAILABLE: "info",
    CapabilityStatus.NOT_REQUESTED: "info",
    CapabilityStatus.SESSION_CLOSED: "info",
    CapabilityStatus.REQUESTING: "warn",
    CapabilityStatus.NEEDS_SETUP: "warn",
    CapabilityStatus.UNKNOWN: "warn",
    CapabilityStatus.NEEDS_PERMISSION: "error",
    CapabilityStatus.REVOKED: "error",
    CapabilityStatus.COMPOSITOR_RESTARTED: "error",
    CapabilityStatus.UNSUPPORTED: "error",
}

_CAPABILITY_COLUMNS = ("diag_cap_col_name", "diag_cap_col_state",
                       "diag_cap_col_backend", "diag_cap_col_scope",
                       "diag_cap_col_detail", "diag_cap_col_fix")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def capability_cells(capability: Capability) -> List[str]:
    """The six cells of one capability row, translated.

    The advice comes from the catalogue when the capability names a key and
    falls back to the headless English text, so a state added without a
    translation still tells the user something.
    """
    advice = ""
    if capability.recovery_key:
        advice = language_wrapper.translate(capability.recovery_key,
                                            capability.recovery)
    return [
        _t(f"cap_name_{capability.name}"),
        _t(f"cap_state_{capability.state.value}"),
        capability.backend,
        _t("cap_scope_desktop" if capability.desktop_wide
           else "cap_scope_xwayland"),
        capability.detail,
        advice or capability.recovery,
    ]


class DiagnosticsTab(TranslatableMixin, QWidget):
    """Run :func:`run_diagnostics` and render the results."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._summary_label = QLabel("-")
        self._table = QTableWidget(0, 4)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch,
        )
        self._capabilities_label = QLabel()
        self._backend_label = QLabel()
        self._capabilities = QTableWidget(0, len(_CAPABILITY_COLUMNS))
        self._capabilities.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._capabilities.setWordWrap(True)
        self._capabilities.horizontalHeader().setSectionResizeMode(
            len(_CAPABILITY_COLUMNS) - 1, QHeaderView.ResizeMode.Stretch,
        )
        self._build_layout()
        self._apply_table_headers()
        self._refresh()
        self._refresh_capabilities()

    def _build_layout(self) -> None:
        # The run command runs from the Actions menu; the tab keeps only
        # the summary label and the result tables.
        root = QVBoxLayout(self)
        root.addWidget(self._summary_label)
        root.addWidget(self._table, stretch=2)
        root.addWidget(self._tr(self._capabilities_label,
                                "diag_capabilities_title"))
        root.addWidget(self._backend_label)
        root.addWidget(self._capabilities, stretch=1)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("diag_run", self._refresh),
            ("diag_capabilities_refresh", self._refresh_capabilities),
            ("diag_input_reask", self._ask_input_again),
            ("diag_input_close", self._end_input_session),
        ]

    def retranslate(self) -> None:
        """Re-apply the registered keys and both tables' own text."""
        super().retranslate()
        self._apply_table_headers()
        self._refresh_capabilities()

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("diag_col_name"), _t("diag_col_severity"),
            _t("diag_col_status"), _t("diag_col_detail"),
        ])
        self._capabilities.setHorizontalHeaderLabels(
            [_t(key) for key in _CAPABILITY_COLUMNS])

    def _refresh(self) -> None:
        report = run_diagnostics()
        summary = report.to_dict()
        if report.ok:
            self._summary_label.setText(_t("diag_summary_ok").format(
                count=summary["count"],
            ))
        else:
            self._summary_label.setText(_t("diag_summary_failed").format(
                failed=summary["failed"], count=summary["count"],
            ))
        self._table.setRowCount(len(report.checks))
        for row, check in enumerate(report.checks):
            cells = [
                check.name,
                check.severity,
                _t("diag_status_ok") if check.ok else _t("diag_status_fail"),
                check.detail,
            ]
            color = _SEVERITY_COLOR.get(check.severity)
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if color is not None and col == 1:
                    item.setForeground(QBrush(color))
                self._table.setItem(row, col, item)

    def _refresh_capabilities(self) -> None:
        """Show the current snapshot. Asks the desktop for nothing."""
        snapshot = probe_capabilities()
        self._backend_label.setText(
            _t("cap_backend_version").replace("{backend}", snapshot.display_server).replace(
                "{version}", snapshot.backend_version or _t("cap_backend_version_unknown")))
        self._capabilities.setRowCount(len(snapshot.capabilities))
        for row, capability in enumerate(snapshot.capabilities):
            color = _SEVERITY_COLOR[_STATE_SEVERITY[capability.state]]
            for col, text in enumerate(capability_cells(capability)):
                item = QTableWidgetItem(text)
                if col == 1:
                    item.setForeground(QBrush(color))
                self._capabilities.setItem(row, col, item)
        self._capabilities.resizeRowsToContents()

    def _ask_input_again(self) -> None:
        """Forget a refused or revoked input session; the next action asks."""
        reset_input_authorisation()
        self._refresh_capabilities()

    def _end_input_session(self) -> None:
        """Close the input session now, which revokes the portal grant."""
        close_input_session()
        self._refresh_capabilities()


__all__ = ["DiagnosticsTab", "capability_cells"]
