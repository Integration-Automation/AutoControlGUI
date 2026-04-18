"""Shell-command and Report-generation tab builders (extracted mixin)."""
from PySide6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.generate_report.generate_html_report import generate_html_report
from je_auto_control.utils.generate_report.generate_json_report import generate_json_report
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml_report
from je_auto_control.utils.shell_process.shell_exec import ShellManager
from je_auto_control.utils.start_exe.start_another_process import start_exe
from je_auto_control.utils.test_record.record_test_class import test_record_instance


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class ShellReportTabsMixin:
    """Provides shell-command and report-generation tab builders/handlers.

    Host widget must expose the TranslatableMixin API (``self._tr(...)``)
    so every label/button registers for live language switching.
    """

    def _build_shell_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        shell_group = self._tr(QGroupBox(), "shell_command_label")
        sg = QVBoxLayout()
        self.shell_input = QLineEdit()
        self.shell_input.setPlaceholderText("echo hello")
        self.shell_exec_btn = self._tr(QPushButton(), "execute_shell")
        self.shell_exec_btn.clicked.connect(self._execute_shell)
        sh = QHBoxLayout()
        sh.addWidget(self.shell_input)
        sh.addWidget(self.shell_exec_btn)
        sg.addLayout(sh)
        shell_group.setLayout(sg)
        layout.addWidget(shell_group)

        exe_group = self._tr(QGroupBox(), "start_exe_label")
        eg = QHBoxLayout()
        self.exe_path_input = QLineEdit()
        self.exe_browse_btn = self._tr(QPushButton(), "browse")
        self.exe_browse_btn.clicked.connect(self._browse_exe)
        self.exe_start_btn = self._tr(QPushButton(), "start_exe")
        self.exe_start_btn.clicked.connect(self._start_exe)
        eg.addWidget(self.exe_path_input)
        eg.addWidget(self.exe_browse_btn)
        eg.addWidget(self.exe_start_btn)
        exe_group.setLayout(eg)
        layout.addWidget(exe_group)

        layout.addWidget(self._tr(QLabel(), "shell_output"))
        self.shell_output_text = QTextEdit()
        self.shell_output_text.setReadOnly(True)
        layout.addWidget(self.shell_output_text)
        tab.setLayout(layout)
        return tab

    def _execute_shell(self):
        try:
            cmd = self.shell_input.text()
            if not cmd:
                return
            mgr = ShellManager()
            mgr.exec_shell(cmd)
            self.shell_output_text.setText(
                f"Executed: {cmd}\n(Check console for output)"
            )
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.shell_output_text.setText(f"Error: {error}")

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self, _t("start_exe_label"), "", "Executable (*.exe);;All (*)",
        )
        if path:
            self.exe_path_input.setText(path)

    def _start_exe(self):
        try:
            path = self.exe_path_input.text()
            if not path:
                return
            start_exe(path)
            self.shell_output_text.setText(f"Started: {path}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.shell_output_text.setText(f"Error: {error}")

    def _build_report_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        tr_group = self._tr(QGroupBox(), "test_record_status")
        tr_h = QHBoxLayout()
        self.tr_enable_btn = self._tr(QPushButton(), "enable_test_record")
        self.tr_enable_btn.clicked.connect(lambda: self._set_test_record(True))
        self.tr_disable_btn = self._tr(QPushButton(), "disable_test_record")
        self.tr_disable_btn.clicked.connect(lambda: self._set_test_record(False))
        self.tr_status_label = QLabel("OFF")
        tr_h.addWidget(self.tr_enable_btn)
        tr_h.addWidget(self.tr_disable_btn)
        tr_h.addWidget(self.tr_status_label)
        tr_group.setLayout(tr_h)
        layout.addWidget(tr_group)

        name_h = QHBoxLayout()
        name_h.addWidget(self._tr(QLabel(), "report_name"))
        self.report_name_input = QLineEdit("autocontrol_report")
        name_h.addWidget(self.report_name_input)
        layout.addLayout(name_h)

        btn_h = QHBoxLayout()
        self.html_report_btn = self._tr(QPushButton(), "generate_html_report")
        self.html_report_btn.clicked.connect(self._gen_html)
        self.json_report_btn = self._tr(QPushButton(), "generate_json_report")
        self.json_report_btn.clicked.connect(self._gen_json)
        self.xml_report_btn = self._tr(QPushButton(), "generate_xml_report")
        self.xml_report_btn.clicked.connect(self._gen_xml)
        btn_h.addWidget(self.html_report_btn)
        btn_h.addWidget(self.json_report_btn)
        btn_h.addWidget(self.xml_report_btn)
        layout.addLayout(btn_h)

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

    def _gen_html(self):
        try:
            name = self.report_name_input.text() or "autocontrol_report"
            generate_html_report(name)
            self.report_result_text.setText(f"HTML report generated: {name}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.report_result_text.setText(f"Error: {error}")

    def _gen_json(self):
        try:
            name = self.report_name_input.text() or "autocontrol_report"
            generate_json_report(name)
            self.report_result_text.setText(f"JSON report generated: {name}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.report_result_text.setText(f"Error: {error}")

    def _gen_xml(self):
        try:
            name = self.report_name_input.text() or "autocontrol_report"
            generate_xml_report(name)
            self.report_result_text.setText(f"XML report generated: {name}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.report_result_text.setText(f"Error: {error}")
