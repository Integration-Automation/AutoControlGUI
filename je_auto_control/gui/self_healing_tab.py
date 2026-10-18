"""Self-healing runtime, fixed-frame comparison and original-step inspection tab.

Fire a template-first / VLM-fallback locate from the GUI and browse the
audit log, or compare explicit versions on provided PNG samples without device effects.
"""
import json
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.healing_evaluation_panel import HealingEvaluationPanel
from je_auto_control.gui.journal_browser import JournalBrowser
from je_auto_control.gui.template_candidate_panel import TemplateCandidatePanel
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.self_healing import (
    HealEvent, HealOutcome, default_heal_log, self_heal_click, self_heal_locate,
    SelfHealRequest, SelfHealRequestError, VerificationRequest, self_heal_run,
)
from je_auto_control.utils.exception.exceptions import AutoControlException


_COLUMNS = ("timestamp", "method", "coordinates",
            "operation", "operation_status", "verified", "duration_ms", "template_path", "description")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def _dispatch(inputs: tuple[Optional[str], Optional[str], float, Optional[list[int]]],
                do_click: bool, verification: str) -> tuple[HealOutcome, Optional[bool]]:
    template, description, threshold, region = inputs
    if verification:
        if not do_click:
            raise SelfHealRequestError(_t("self_heal_verification_needs_click"))
        result = self_heal_run(SelfHealRequest(
            template_path=template, description=description, detect_threshold=threshold, screen_region=region,
            operation="click", verification=VerificationRequest(description=verification)))
        return result.outcome, result.verified
    implementation = self_heal_click if do_click else self_heal_locate
    return implementation(template_path=template, description=description,
                           detect_threshold=threshold, screen_region=region), None


# pylint: disable-next=too-many-instance-attributes  # reason: the tab owns separate runtime and comparison controls
class SelfHealingTab(TranslatableMixin, QWidget):
    """Trigger self-heal attempts and browse the audit log."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._template_input = QLineEdit()
        self._description_input = QLineEdit()
        self._region_input = QLineEdit()
        self._verification_input = QLineEdit()
        self._threshold = QDoubleSpinBox()
        self._threshold.setRange(0.0, 1.0)
        self._threshold.setSingleStep(0.05)
        self._threshold.setValue(0.9)
        self._click_check = QCheckBox()
        self._status = QLabel()
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._table = QTableWidget(0, len(_COLUMNS))
        self._details = QPlainTextEdit()
        self._details.setReadOnly(True)
        self._group_box = QGroupBox()
        self._events: list[HealEvent] = []
        # pylint: disable-next=no-member  # reason: PySide binds this Qt signal at runtime
        self._table.itemSelectionChanged.connect(self._show_event)
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_translations()

    # --- layout ----------------------------------------------------

    def _build_layout(self) -> None:
        # Browse/locate/click/refresh/clear commands run from the Actions
        # menu; the tab keeps only the inputs, the log table, and the status.
        root = QVBoxLayout(self)
        runtime = QWidget()
        runtime_layout = QVBoxLayout(runtime)
        runtime_layout.addWidget(self._build_form_group())
        views = QSplitter(Qt.Orientation.Vertical)
        views.addWidget(self._table)
        views.addWidget(self._details)
        runtime_layout.addWidget(views, stretch=1)
        runtime_layout.addWidget(self._status)
        self._views = QTabWidget()
        self._evaluation = HealingEvaluationPanel(self)
        self._source = JournalBrowser(self)
        self._candidates = TemplateCandidatePanel(self)
        self._views.addTab(runtime, "")
        self._views.addTab(self._evaluation, "")
        self._views.addTab(self._source, "")
        self._views.addTab(self._candidates, "")
        root.addWidget(self._views, stretch=1)
        self._apply_translations()
        self.refresh_log()

    def _build_form_group(self) -> QGroupBox:
        group = self._group_box
        form = QFormLayout(group)
        form.addRow(QLabel(), self._template_input)
        form.addRow(QLabel(), self._description_input)
        form.addRow(QLabel(), self._threshold)
        form.addRow(QLabel(), self._region_input)
        form.addRow(QLabel(), self._verification_input)
        form.addRow(QLabel(), self._click_check)
        return group

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("self_heal_browse", self._on_browse_template),
            ("self_heal_locate_btn", self._on_locate),
            ("self_heal_click_btn", self._on_click),
            ("self_heal_refresh", self.refresh_log),
            ("self_heal_clear", self._on_clear_log),
            ("self_heal_source_open", self._on_source),
        ] + self._evaluation.menu_actions() + self._source.menu_actions() + self._candidates.menu_actions()

    # --- translation -----------------------------------------------

    def _apply_translations(self) -> None:
        self._views.setTabText(0, _t("healing_eval_log"))
        self._views.setTabText(1, _t("healing_eval_heading"))
        self._views.setTabText(2, _t("self_heal_source_heading"))
        self._views.setTabText(3, _t("template_candidate_heading"))
        self._evaluation.retranslate()
        self._source.retranslate()
        self._candidates.retranslate()
        self._group_box.setTitle(_t("self_heal_form_title"))
        self._template_input.setPlaceholderText(_t("self_heal_template_placeholder"))
        self._description_input.setPlaceholderText(_t("self_heal_desc_placeholder"))
        self._region_input.setPlaceholderText(_t("self_heal_region_placeholder"))
        self._verification_input.setPlaceholderText(_t("self_heal_verification_placeholder"))
        self._click_check.setText(_t("self_heal_click_check"))
        layout = self._group_box.layout()
        if isinstance(layout, QFormLayout):
            labels = (
                "self_heal_template_label", "self_heal_desc_label",
                "self_heal_threshold_label", "self_heal_region_label", "self_heal_verification_label", "",
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
        try:
            raw = self._region_input.text().strip()
            region = json.loads(raw) if raw else None
            if region is not None and not isinstance(region, list):
                raise ValueError(_t("self_heal_region_placeholder"))
        except ValueError as error:
            self._status.setText(f"{_t('self_heal_error')}: {error}")
            return None
        return template, description, float(self._threshold.value()), region

    def _on_locate(self) -> None:
        self._run(do_click=False)

    def _on_click(self) -> None:
        self._run(do_click=True)

    def _run(self, *, do_click: bool) -> None:
        inputs = self._collect_inputs()
        if inputs is None:
            return
        try:
            outcome, verified = _dispatch(inputs, do_click or self._click_check.isChecked(),
                                           self._verification_input.text().strip())
        except (AutoControlException, OSError, ValueError, RuntimeError) as error:
            self._status.setText(f"{_t('self_heal_error')}: {error}")
            self.refresh_log()
            return
        self._report_outcome(outcome)
        if verified is not None:
            self._status.setText(_t("self_heal_verification_passed" if verified else "self_heal_verification_failed"))
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
        self._events = events
        self._table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = (
                event.timestamp, event.method,
                _format_coordinates(event.coordinates),
                event.operation, event.operation_status,
                _t("self_heal_unknown") if event.verified is None else str(event.verified),
                f"{event.duration_ms:.1f}",
                event.template_path or "", event.description or "",
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._table.setItem(row, col, item)
        self._table.resizeColumnsToContents()
        for name in ("template_path", "description"):
            column = _COLUMNS.index(name)
            self._table.setColumnWidth(column, min(self._table.columnWidth(column), 240))
        self._show_event()

    def _show_event(self) -> None:
        self._source.set_links([])
        row = self._table.currentRow()
        if row < 0 or row >= len(self._events):
            self._details.clear()
            return
        self._details.setPlainText(json.dumps(self._events[row].to_dict(), ensure_ascii=False, indent=2))

    def _on_source(self) -> None:
        row = self._table.currentRow()
        if not 0 <= row < len(self._events):
            self._status.setText(_t("self_heal_source_missing"))
            return
        event = self._events[row]
        values = (event.journal_path, event.run_id, event.step_id)
        if not all(isinstance(value, str) and value for value in values):
            self._status.setText(_t("self_heal_source_missing"))
            return
        self._source.open_source(str(event.journal_path), str(event.run_id), str(event.step_id))
        self._views.setCurrentWidget(self._source)

    # pylint: disable-next=invalid-name  # reason: Qt override
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802  # reason: Qt override
        """Cancel source inspection immediately when the owning tab closes."""
        self._source.cancel()
        self._candidates.cancel()
        super().closeEvent(event)


def _format_coordinates(coords) -> str:
    if coords is None:
        return ""
    return f"({coords[0]}, {coords[1]})"


__all__ = ["SelfHealingTab"]
