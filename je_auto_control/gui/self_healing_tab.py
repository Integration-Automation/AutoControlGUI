"""Self-Healing Locator tab.

Fire a template-first / VLM-fallback locate from the GUI and browse the
audit log of every healing attempt the runtime has performed. The second
group measures locator versions against a labelled dataset -- the result is
a comparison table, one version per row, with the full report beneath it --
and walks a candidate template revision through propose / preview / accept /
revert; every one of those is a call into ``utils.self_healing`` and nothing
more.
"""
import functools
import json
from typing import Callable, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._tab_task import TabTask
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.self_healing import (
    COMPARISON_COLUMNS, HealOutcome, accept_template_revision, comparison_rows,
    default_heal_log, evaluate_healing_dataset, list_template_revisions,
    preview_template_revision, propose_template_revision,
    revert_template_revision, self_heal_click, self_heal_locate,
)
from je_auto_control.utils.exception.exceptions import AutoControlException


_COLUMNS = ("timestamp", "method", "coordinates",
            "template_path", "description", "duration_ms",
            "locator_version", "action_verified")

_SLOT_ERRORS = (AutoControlException, OSError, ValueError, RuntimeError)
_IMAGE_FILTER = "Images (*.png *.jpg *.bmp);;All (*)"


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
        self._verify_input = QLineEdit()
        self._status = QLabel()
        self._table = QTableWidget(0, len(_COLUMNS))
        self._dataset_input = QLineEdit()
        self._candidate_input = QLineEdit()
        self._revision_input = QLineEdit()
        self._compare_table = QTableWidget(0, len(COMPARISON_COLUMNS))
        self._compare_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._compare_table.verticalHeader().setVisible(False)
        self._report_view = QPlainTextEdit()
        self._report_view.setReadOnly(True)
        self._runs = TabTask(self)
        self._runs.result.connect(self._show_heal_outcome)
        self._runs.error.connect(self._show_heal_error)
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
        root.addWidget(self._build_measure_group())
        root.addWidget(self._compare_table, stretch=1)
        root.addWidget(self._report_view, stretch=1)
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
        form.addRow(QLabel(), self._verify_input)
        self._group_box = group
        return group

    def _build_measure_group(self) -> QGroupBox:
        group = QGroupBox()
        form = QFormLayout(group)
        form.addRow(QLabel(), self._dataset_input)
        form.addRow(QLabel(), self._candidate_input)
        form.addRow(QLabel(), self._revision_input)
        self._measure_box = group
        return group

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("self_heal_browse", self._on_browse_template),
            ("self_heal_locate_btn", self._on_locate),
            ("self_heal_click_btn", self._on_click),
            ("self_heal_refresh", self.refresh_log),
            ("self_heal_clear", self._on_clear_log),
            ("self_heal_browse_dataset", self._on_browse_dataset),
            ("self_heal_evaluate", self._on_evaluate),
            ("self_heal_browse_candidate", self._on_browse_candidate),
            ("self_heal_rev_propose", self._on_propose_revision),
            ("self_heal_rev_preview", self._on_preview_revision),
            ("self_heal_rev_accept", self._on_accept_revision),
            ("self_heal_rev_revert", self._on_revert_revision),
            ("self_heal_rev_list", self._on_list_revisions),
        ]

    # --- translation -----------------------------------------------

    def _apply_translations(self) -> None:
        self._group_box.setTitle(_t("self_heal_form_title"))
        self._template_input.setPlaceholderText(_t("self_heal_template_placeholder"))
        self._description_input.setPlaceholderText(_t("self_heal_desc_placeholder"))
        self._click_check.setText(_t("self_heal_click_check"))
        self._verify_input.setPlaceholderText(_t("self_heal_verify_placeholder"))
        _set_form_labels(self._group_box, (
            "self_heal_template_label", "self_heal_desc_label",
            "self_heal_threshold_label", "", "self_heal_verify_label",
        ))
        self._measure_box.setTitle(_t("self_heal_measure_title"))
        self._dataset_input.setPlaceholderText(_t("self_heal_dataset_placeholder"))
        self._candidate_input.setPlaceholderText(_t("self_heal_candidate_placeholder"))
        self._revision_input.setPlaceholderText(_t("self_heal_revision_placeholder"))
        self._report_view.setPlaceholderText(_t("self_heal_report_placeholder"))
        _set_form_labels(self._measure_box, (
            "self_heal_dataset_label", "self_heal_candidate_label",
            "self_heal_revision_label",
        ))
        headers = [_t(f"self_heal_col_{name}") for name in _COLUMNS]
        self._table.setHorizontalHeaderLabels(headers)
        self._compare_table.setHorizontalHeaderLabels(
            [_t(f"self_heal_cmp_{name}") for name in COMPARISON_COLUMNS])

    # --- actions ---------------------------------------------------

    def _on_browse_template(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self, _t("self_heal_browse"), "", _IMAGE_FILTER,
        )
        if path:
            self._template_input.setText(path)

    def _on_browse_dataset(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self, _t("self_heal_browse_dataset"), "", "JSON (*.json);;All (*)",
        )
        if path:
            self._dataset_input.setText(path)

    def _on_browse_candidate(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self, _t("self_heal_browse_candidate"), "", _IMAGE_FILTER,
        )
        if path:
            self._candidate_input.setText(path)

    # --- measurement and template revisions -------------------------

    def _show(self, call: Callable[[], object]) -> Optional[object]:
        """Run a headless call; show its JSON result, or its error in the status."""
        try:
            result = call()
        except _SLOT_ERRORS as error:
            self._status.setText(f"{_t('self_heal_error')}: {error}")
            return None
        self._report_view.setPlainText(
            json.dumps(result, ensure_ascii=False, indent=2, default=str))
        self._status.setText(_t("self_heal_done"))
        return result

    def _revision_id(self) -> Optional[str]:
        revision_id = self._revision_input.text().strip()
        if not revision_id:
            self._status.setText(_t("self_heal_revision_required"))
            return None
        return revision_id

    def _on_evaluate(self) -> None:
        dataset = self._dataset_input.text().strip()
        if not dataset:
            self._status.setText(_t("self_heal_dataset_required"))
            return
        result = self._show(lambda: evaluate_healing_dataset(dataset))
        if isinstance(result, dict):
            self._fill_comparison(result)
            self._status.setText(_t(
                "self_heal_eval_passed" if result.get("passed") else "self_heal_eval_failed"))

    def _fill_comparison(self, report: dict) -> None:
        """Show an evaluation report as one row per version, baseline first."""
        rows = comparison_rows(report)
        self._compare_table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for col, name in enumerate(COMPARISON_COLUMNS):
                text = str(values[name])
                if name == "version" and values["baseline"]:
                    text = _t("self_heal_cmp_baseline").replace("{name}", text)
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._compare_table.setItem(row, col, item)
        self._compare_table.resizeColumnsToContents()

    def _on_propose_revision(self) -> None:
        template = self._template_input.text().strip()
        candidate = self._candidate_input.text().strip()
        if not template or not candidate:
            self._status.setText(_t("self_heal_propose_required"))
            return
        result = self._show(
            lambda: propose_template_revision(template, candidate).to_dict())
        if isinstance(result, dict):
            self._revision_input.setText(str(result["revision_id"]))

    def _on_preview_revision(self) -> None:
        revision_id = self._revision_id()
        if revision_id is None:
            return
        dataset = self._dataset_input.text().strip() or None
        threshold = float(self._threshold.value())
        self._show(lambda: preview_template_revision(
            revision_id, dataset_path=dataset, detect_threshold=threshold))

    def _on_accept_revision(self) -> None:
        revision_id = self._revision_id()
        if revision_id is None:
            return
        self._show(lambda: self._accept(revision_id))

    def _accept(self, revision_id: str) -> dict:
        """Accept a validated revision; an unvalidated one only after a prompt."""
        pending = {item.revision_id: item for item in list_template_revisions()}
        revision = pending.get(revision_id)
        allow = False
        if revision is not None and not revision.validated:
            reply = QMessageBox.question(
                self, _t("self_heal_rev_accept"), _t("self_heal_accept_unvalidated"),
            )
            if reply != QMessageBox.Yes:
                return {"accepted": False, "revision_id": revision_id}
            allow = True
        return accept_template_revision(revision_id, allow_unvalidated=allow).to_dict()

    def _on_revert_revision(self) -> None:
        revision_id = self._revision_id()
        if revision_id is None:
            return
        self._show(lambda: revert_template_revision(revision_id).to_dict())

    def _on_list_revisions(self) -> None:
        self._show(lambda: [item.to_dict() for item in list_template_revisions()])

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
        click = do_click or self._click_check.isChecked()
        try:
            # Read on the GUI thread: the check is typed into a widget.
            verify = self._verify_spec() if click else None
        except ValueError as error:
            self._status.setText(f"{_t('self_heal_error')}: {error}")
            return
        # A template search and, on a miss, a VLM call: off the GUI thread.
        if not self._runs.start(functools.partial(
                _heal, click, template, description, threshold, verify)):
            return
        self._status.setText(_t("task_running"))

    def _show_heal_error(self, error: object) -> None:
        self._status.setText(f"{_t('self_heal_error')}: {error}")

    def _show_heal_outcome(self, outcome: HealOutcome) -> None:
        self._report_outcome(outcome)
        self.refresh_log()

    def _verify_spec(self) -> Optional[dict]:
        """The post-click check typed as JSON, or ``None`` when the field is empty."""
        text = self._verify_input.text().strip()
        if not text:
            return None
        spec = json.loads(text)  # a ValueError is shown by the caller
        if not isinstance(spec, dict):
            raise ValueError(_t("self_heal_verify_invalid"))
        return spec

    def _report_outcome(self, outcome: HealOutcome) -> None:
        if not outcome.found:
            self._status.setText(_t("self_heal_miss"))
            return
        suffix = f" ({outcome.method})"
        if outcome.action is not None:
            suffix += " · " + _format_verified(outcome.action, outcome.action_verified)
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
                event.locator_version or "",
                _format_verified(event.action, event.action_verified),
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._table.setItem(row, col, item)
        self._table.resizeColumnsToContents()


def _heal(click: bool, template: str, description: str, threshold: float,
          verify: Optional[dict] = None) -> HealOutcome:
    """Worker thread: one locate (or locate-and-click) attempt."""
    if click:
        return self_heal_click(template_path=template, description=description,
                               detect_threshold=threshold, verify=verify)
    return self_heal_locate(template_path=template, description=description,
                            detect_threshold=threshold)


def _format_coordinates(coords) -> str:
    if coords is None:
        return ""
    return f"({coords[0]}, {coords[1]})"


def _format_verified(action: Optional[str], verified: Optional[bool]) -> str:
    """Empty for a bare locate; otherwise whether the action was checked."""
    if action is None:
        return ""
    if verified is None:
        return _t("self_heal_verified_unknown")
    return _t("self_heal_verified_yes" if verified else "self_heal_verified_no")


def _set_form_labels(group: QGroupBox, keys: Sequence[str]) -> None:
    """Translate the label column of ``group``'s form, row by row."""
    layout = group.layout()
    if not isinstance(layout, QFormLayout):
        return
    for row, key in enumerate(keys):
        item = layout.itemAt(row, QFormLayout.LabelRole)
        if item is not None and isinstance(item.widget(), QLabel):
            item.widget().setText(_t(key) if key else "")


__all__ = ["SelfHealingTab"]
