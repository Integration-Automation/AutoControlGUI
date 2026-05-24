"""WebRunner bridge tab: drive ``je_web_runner`` from the GUI.

A thin wrapper over :mod:`je_auto_control.utils.webrunner_bridge` — the
convenience actions (open / quit / screenshot) cover the common flow,
and a free-form ``WR_*`` runner exposes the full 440-command surface.
"""
import json
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMessageBox, QPushButton, QTextEdit,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.webrunner_bridge import (
    WebRunnerBridgeError, is_webrunner_available, list_webrunner_commands,
    run_webrunner_action, web_open, web_quit, web_screenshot,
)


_BRIDGE_ERRORS = (WebRunnerBridgeError, OSError, ValueError, RuntimeError)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class WebRunnerTab(TranslatableMixin, QWidget):
    """Quick-open / quit / screenshot + free-form WR_* runner."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._available_label = QLabel()
        self._url_input = QLineEdit()
        self._browser_input = QComboBox()
        self._browser_input.addItems(["chrome", "firefox", "edge", "safari"])
        self._screenshot_input = QLineEdit()
        self._action_input = QLineEdit()
        self._params_input = QTextEdit()
        self._params_input.setMaximumHeight(120)
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._commands_list = QListWidget()
        self._build_layout()
        self.refresh_availability()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self.refresh_availability()

    # --- layout ----------------------------------------------------

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(self._available_label)
        root.addWidget(self._build_convenience_group())
        root.addWidget(self._build_freeform_group())
        commands_row = QHBoxLayout()
        commands_row.addWidget(QLabel(_t("web_commands_label")), stretch=0)
        commands_row.addWidget(self._commands_list, stretch=1)
        root.addLayout(commands_row, stretch=1)
        root.addWidget(QLabel(_t("web_output_label")))
        root.addWidget(self._output, stretch=2)

    def _build_convenience_group(self) -> QGroupBox:
        group = QGroupBox(_t("web_convenience_title"))
        form = QFormLayout(group)
        form.addRow(QLabel(_t("web_url_label")), self._url_input)
        form.addRow(QLabel(_t("web_browser_label")), self._browser_input)
        shot_row = QHBoxLayout()
        shot_row.addWidget(self._screenshot_input, stretch=1)
        browse = QPushButton(_t("web_browse"))
        browse.clicked.connect(self._on_browse_screenshot)
        shot_row.addWidget(browse)
        form.addRow(QLabel(_t("web_screenshot_label")), shot_row)
        actions_row = QHBoxLayout()
        for label_key, slot in (
                ("web_open_btn", self._on_open),
                ("web_quit_btn", self._on_quit),
                ("web_screenshot_btn", self._on_screenshot),
        ):
            btn = QPushButton(_t(label_key))
            btn.clicked.connect(slot)
            actions_row.addWidget(btn)
        actions_row.addStretch()
        form.addRow(QLabel(), actions_row)
        return group

    def _build_freeform_group(self) -> QGroupBox:
        group = QGroupBox(_t("web_freeform_title"))
        form = QFormLayout(group)
        self._action_input.setPlaceholderText(_t("web_action_placeholder"))
        self._params_input.setPlaceholderText(
            _t("web_params_placeholder"),
        )
        form.addRow(QLabel(_t("web_action_label")), self._action_input)
        form.addRow(QLabel(_t("web_params_label")), self._params_input)
        run_row = QHBoxLayout()
        run = QPushButton(_t("web_run_btn"))
        run.clicked.connect(self._on_run_freeform)
        refresh = QPushButton(_t("web_refresh_btn"))
        refresh.clicked.connect(self._on_refresh_commands)
        run_row.addWidget(run)
        run_row.addWidget(refresh)
        run_row.addStretch()
        form.addRow(QLabel(), run_row)
        return group

    # --- availability ---------------------------------------------

    def refresh_availability(self) -> None:
        available = is_webrunner_available()
        key = "web_available" if available else "web_unavailable"
        self._available_label.setText(_t(key))
        self._available_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse,
        )

    # --- handlers -------------------------------------------------

    def _on_browse_screenshot(self) -> None:
        path, _selected = QFileDialog.getSaveFileName(
            self, _t("web_browse"), "", "PNG (*.png);;All (*)",
        )
        if path:
            self._screenshot_input.setText(path)

    def _on_open(self) -> None:
        url = self._url_input.text().strip()
        if not url:
            QMessageBox.warning(self, _t("web_open_btn"),
                                _t("web_url_required"))
            return
        self._run_safe(
            lambda: web_open(url, browser=self._browser_input.currentText()),
            "web_open_btn",
        )

    def _on_quit(self) -> None:
        self._run_safe(web_quit, "web_quit_btn")

    def _on_screenshot(self) -> None:
        path = self._screenshot_input.text().strip()
        if not path:
            QMessageBox.warning(self, _t("web_screenshot_btn"),
                                _t("web_screenshot_required"))
            return
        self._run_safe(lambda: web_screenshot(path), "web_screenshot_btn")

    def _on_run_freeform(self) -> None:
        action = self._action_input.text().strip()
        if not action:
            QMessageBox.warning(self, _t("web_run_btn"),
                                _t("web_action_required"))
            return
        params_text = self._params_input.toPlainText().strip()
        params = {}
        if params_text:
            try:
                params = json.loads(params_text)
            except ValueError as error:
                self._output.append(f"params JSON error: {error}")
                return
        self._run_safe(
            lambda: run_webrunner_action(
                {"action": action, "params": params},
            ),
            "web_run_btn",
        )

    def _on_refresh_commands(self) -> None:
        self._commands_list.clear()
        try:
            for name in list_webrunner_commands():
                self._commands_list.addItem(name)
        except _BRIDGE_ERRORS as error:
            self._output.append(f"{_t('web_error')}: {error}")

    def _run_safe(self, callable_, label_key: str) -> None:
        try:
            result = callable_()
        except _BRIDGE_ERRORS as error:
            self._output.append(f"{_t(label_key)} {_t('web_error')}: {error}")
            return
        rendered = (
            result if isinstance(result, str)
            else json.dumps(result, default=str, ensure_ascii=False)
        )
        self._output.append(f"{_t(label_key)}: {rendered}")


__all__ = ["WebRunnerTab"]
