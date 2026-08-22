"""Report-generation tab builder (extracted mixin)."""
from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.generate_report.generate_html_report import generate_html_report
from je_auto_control.utils.generate_report.generate_json_report import generate_json_report
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml_report
from je_auto_control.utils.test_record.record_test_class import test_record_instance


class ReportTabMixin:
    """Provides the report-generation tab builder/handlers.

    Host widget must expose the TranslatableMixin API (``self._tr(...)``)
    so every label/button registers for live language switching.
    """

    if TYPE_CHECKING:
        # Declared, never defined: the widget this mixin is mixed into owns
        # every one of these. The block is stripped at runtime, so nothing
        # here can shadow what the host actually binds.
        _tr: Callable[..., Any]

    def _build_report_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        # Enable/disable recording and report generation run from the
        # Actions menu; the tab keeps only status, name input, and result.
        tr_group = self._tr(QGroupBox(), "test_record_status")
        tr_h = QHBoxLayout()
        self.tr_status_label = QLabel("OFF")
        tr_h.addWidget(self.tr_status_label)
        tr_group.setLayout(tr_h)
        layout.addWidget(tr_group)

        name_h = QHBoxLayout()
        name_h.addWidget(self._tr(QLabel(), "report_name"))
        self.report_name_input = QLineEdit("autocontrol_report")
        name_h.addWidget(self.report_name_input)
        layout.addLayout(name_h)

        layout.addWidget(self._tr(QLabel(), "report_result"))
        self.report_result_text = QTextEdit()
        self.report_result_text.setReadOnly(True)
        layout.addWidget(self.report_result_text)
        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def _set_test_record(self, enable: bool):
        test_record_instance.set_record_enable(enable)
        self.tr_status_label.setText("ON" if enable else "OFF")

    def _enable_test_record(self):
        self._set_test_record(True)

    def _disable_test_record(self):
        self._set_test_record(False)

    def _gen_html(self):
        try:
            name = self.report_name_input.text() or "autocontrol_report"
            generate_html_report(name)
            self.report_result_text.setText(f"HTML report generated: {name}")
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            self.report_result_text.setText(f"Error: {error}")

    def _gen_json(self):
        try:
            name = self.report_name_input.text() or "autocontrol_report"
            generate_json_report(name)
            self.report_result_text.setText(f"JSON report generated: {name}")
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            self.report_result_text.setText(f"Error: {error}")

    def _gen_xml(self):
        try:
            name = self.report_name_input.text() or "autocontrol_report"
            generate_xml_report(name)
            self.report_result_text.setText(f"XML report generated: {name}")
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            self.report_result_text.setText(f"Error: {error}")
