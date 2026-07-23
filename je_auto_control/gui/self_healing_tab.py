"""Self-Healing Locator tab.

Fire a template-first / VLM-fallback locate from the GUI and browse the
audit log of every healing attempt the runtime has performed.
"""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QMessageBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.self_healing import (
    HealOutcome, default_heal_log, self_heal_click, self_heal_locate,
)


_COLUMNS = ("timestamp", "method", "coordinates",
            "template_path", "description", "duration_ms")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class SelfHealingTab(TranslatableMixin, QWidget):
    """Trigger self-heal attempts and browse the audit log."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._template_input = QLineEdit()
        self._description_input = QLineEdit()
        self._threshold = QDoubleSpinBox()
        self._threshold.setRange(0.0, 1.0)
        self._threshold.setSingleStep(0.05)
        self._threshold.setValue(0.9)
        self._click_check = QCheckBox()
        self._status = QLabel()
        self._table = QTableWidget(0, len(_COLUMNS))
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_translations()

    # --- layout ----------------------------------------------------

    def _build_layout(self) -> None:
        # Browse/locate/click/refresh/clear commands run from the Actions
        # menu; the tab keeps only the inputs, the log table, and the status.
        root = QVBoxLayout(self)
        root.addWidget(self._build_form_group())
        root.addWidget(self._table, stretch=1)
        root.addWidget(self._status)
        self._apply_translations()
        self.refresh_log()

    def _build_form_group(self) -> QGroupBox:
        group = QGroupBox()
        form = QFormLayout(group)
        form.addRow(QLabel(), self._template_input)
        form.addRow(QLabel(), self._description_input)
        form.addRow(QLabel(), self._threshold)
        form.addRow(QLabel(), self._click_check)
        self._group_box = group
        return group

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("self_heal_browse", self._on_browse_template),
            ("self_heal_locate_btn", self._on_locate),
            ("self_heal_click_btn", self._on_click),
            ("self_heal_refresh", self.refresh_log),
            ("self_heal_clear", self._on_clear_log),
        ]

    # --- translation -----------------------------------------------

    def _apply_translations(self) -> None:
        self._group_box.setTitle(_t("self_heal_form_title"))
        self._template_input.setPlaceholderText(_t("self_heal_template_placeholder"))
        self._description_input.setPlaceholderText(_t("self_heal_desc_placeholder"))
        self._click_check.setText(_t("self_heal_click_check"))
        layout = self._group_box.layout()
        if isinstance(layout, QFormLayout):
            labels = (
                "self_heal_template_label", "self_heal_desc_label",
                "self_heal_threshold_label", "",
            )
            for row, key in enumerate(labels):
                item = layout.itemAt(row, QFormLayout.LabelRole)
                if item is not None and isinstance(item.widget(), QLabel):
                    item.widget().setText(_t(key) if key else "")
        headers = [_t(f"self_heal_col_{name}") for name in _COLUMNS]
        self._table.setHorizontalHeaderLabels(headers)

    # --- actions ---------------------------------------------------

    def _on_browse_template(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self, _t("self_heal_browse"), "",
            "Images (*.png *.jpg *.bmp);;All (*)",
        )
        if path:
            self._template_input.setText(path)

    def _collect_inputs(self):
        template = self._template_input.text().strip() or None
        description = self._description_input.text().strip() or None
        if template is None and description is None:
            self._status.setText(_t("self_heal_inputs_required"))
            return None
        return template, description, float(self._threshold.value())

    def _on_locate(self) -> None:
        self._run(do_click=False)

    def _on_click(self) -> None:
        self._run(do_click=True)

    def _run(self, *, do_click: bool) -> None:
        inputs = self._collect_inputs()
        if inputs is None:
            return
        template, description, threshold = inputs
        try:
            if do_click or self._click_check.isChecked():
                outcome = self_heal_click(
                    template_path=template, description=description,
                    detect_threshold=threshold,
                )
            else:
                outcome = self_heal_locate(
                    template_path=template, description=description,
                    detect_threshold=threshold,
                )
        except (OSError, ValueError, RuntimeError) as error:
            self._status.setText(f"{_t('self_heal_error')}: {error}")
            return
        self._report_outcome(outcome)
        self.refresh_log()

    def _report_outcome(self, outcome: HealOutcome) -> None:
        if not outcome.found:
            self._status.setText(_t("self_heal_miss"))
            return
        suffix = f" ({outcome.method})"
        coords = outcome.coordinates or (0, 0)
        text = _t("self_heal_hit").replace("{x}", str(coords[0])) \
                                   .replace("{y}", str(coords[1]))
        self._status.setText(text + suffix)

    def _on_clear_log(self) -> None:
        reply = QMessageBox.question(
            self, _t("self_heal_clear"), _t("self_heal_clear_confirm"),
        )
        if reply != QMessageBox.Yes:
            return
        default_heal_log.clear()
        self.refresh_log()

    def refresh_log(self) -> None:
        """Reload the table from the on-disk audit log."""
        events = default_heal_log.list_events(limit=200)
        self._table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = (
                event.timestamp, event.method,
                _format_coordinates(event.coordinates),
                event.template_path or "", event.description or "",
                f"{event.duration_ms:.1f}",
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._table.setItem(row, col, item)
        self._table.resizeColumnsToContents()


def _format_coordinates(coords) -> str:
    if coords is None:
        return ""
    return f"({coords[0]}, {coords[1]})"


__all__ = ["SelfHealingTab"]
