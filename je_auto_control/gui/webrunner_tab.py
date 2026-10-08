"""WebRunner bridge tab: drive ``je_web_runner`` from the GUI.

A thin wrapper over :mod:`je_auto_control.utils.webrunner_bridge` — the
convenience actions (open / quit / screenshot) cover the common flow,
and a free-form ``WR_*`` runner exposes every command WebRunner registers.
Every bridge call drives a browser over the network, so it runs off the GUI
thread, one at a time.
"""
import functools
import json
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMessageBox, QTextEdit,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._dispose import release_resources
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._tab_task import TabTask
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
        self._runs = TabTask(self)   # tag: the label key of the command that is running
        self._runs.result.connect(self._show_result)
        self._runs.error.connect(self._show_error)
        self._build_layout()
        self.refresh_availability()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self.refresh_availability()

    # --- layout ----------------------------------------------------

    def _build_layout(self) -> None:
        # Browse/open/quit/screenshot/run/refresh commands run from the
        # Actions menu; the tab keeps only the inputs, list, and output.
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

    def dispose(self) -> None:
        """Release what the tab holds beyond its widgets: the command still running in the background.

        A script run is stopped; other work cannot be interrupted, so it runs to its end and its
        result is dropped. Called by ``close_tab(key, release=True)``; safe to call twice.
        """
        release_resources(self)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("web_browse", self._on_browse_screenshot),
            ("web_open_btn", self._on_open),
            ("web_quit_btn", self._on_quit),
            ("web_screenshot_btn", self._on_screenshot),
            ("web_run_btn", self._on_run_freeform),
            ("web_refresh_btn", self._on_refresh_commands),
        ]

    def _build_convenience_group(self) -> QGroupBox:
        group = QGroupBox(_t("web_convenience_title"))
        form = QFormLayout(group)
        form.addRow(QLabel(_t("web_url_label")), self._url_input)
        form.addRow(QLabel(_t("web_browser_label")), self._browser_input)
        form.addRow(QLabel(_t("web_screenshot_label")), self._screenshot_input)
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
        return group

    # --- availability ---------------------------------------------

    def refresh_availability(self) -> None:
        available = is_webrunner_available()
        key = "web_available" if available else "web_unavailable"
        self._available_label.setText(_t(key))
        self._available_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse,
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
            functools.partial(web_open, url, browser=self._browser_input.currentText()),
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
        self._run_safe(functools.partial(web_screenshot, path), "web_screenshot_btn")

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
            functools.partial(run_webrunner_action, {"action": action, "params": params}),
            "web_run_btn",
        )

    def _on_refresh_commands(self) -> None:
        self._commands_list.clear()
        try:
            for name in list_webrunner_commands():
                self._commands_list.addItem(name)
        except _BRIDGE_ERRORS as error:
            self._output.append(f"{_t('web_error')}: {error}")

    def _run_safe(self, callable_: Callable[[], Any], label_key: str) -> None:
        """Run one bridge call off the GUI thread; ``callable_`` must not hold a widget."""
        if not self._runs.start(callable_, tag=label_key):
            self._output.append(_t("task_busy"))

    def _show_error(self, error: object) -> None:
        self._output.append(f"{_t(self._runs.tag)} {_t('web_error')}: {error}")

    def _show_result(self, result: object) -> None:
        rendered = (
            result if isinstance(result, str)
            else json.dumps(result, default=str, ensure_ascii=False)
        )
        self._output.append(f"{_t(self._runs.tag)}: {rendered}")


__all__ = ["WebRunnerTab"]
