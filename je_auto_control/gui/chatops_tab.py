"""Chat-Ops tab: test slash commands locally before wiring them to Slack.

A command is dispatched off the GUI thread (``/run`` executes a whole script),
one at a time, as a stoppable executor run.
"""
import functools
from typing import Any, Optional

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._dispose import release_resources
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._tab_task import TabTask, was_stopped
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.chatops import (
    CommandRouter, register_chatops_default_commands,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def _dispatch(router: CommandRouter, message: str, context: dict) -> Any:
    """Worker thread: route one message; the router is not touched by the GUI meanwhile."""
    return router.dispatch(message, context=context)


class ChatOpsTab(TranslatableMixin, QWidget):
    """Free-form router playground: pick a script root, type ``/run …``."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._router = CommandRouter()
        register_chatops_default_commands(self._router)
        self._script_root = QLineEdit()
        self._command_input = QLineEdit()
        self._command_input.returnPressed.connect(self._on_send)
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._pending_message = ""
        self._runs = TabTask(self)
        self._runs.result.connect(self._show_result)
        self._runs.error.connect(self._show_error)
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_translations()

    def _build_layout(self) -> None:
        # Browse/send commands run from the Actions menu; the tab keeps
        # only the root/command inputs and the output log.
        root = QVBoxLayout(self)
        root_row = QHBoxLayout()
        self._root_label = QLabel()
        root_row.addWidget(self._root_label)
        root_row.addWidget(self._script_root, stretch=1)
        root.addLayout(root_row)

        cmd_row = QHBoxLayout()
        self._cmd_label = QLabel()
        cmd_row.addWidget(self._cmd_label)
        cmd_row.addWidget(self._command_input, stretch=1)
        root.addLayout(cmd_row)

        self._output_label = QLabel()
        root.addWidget(self._output_label)
        root.addWidget(self._output, stretch=1)
        self._apply_translations()

    def dispose(self) -> None:
        """Release what the tab holds beyond its widgets: the command still running in the background.

        A script run is stopped; other work cannot be interrupted, so it runs to its end and its
        result is dropped. Called by ``close_tab(key, release=True)``; safe to call twice.
        """
        release_resources(self)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("chatops_browse_btn", self._on_browse),
            ("chatops_send_btn", self._on_send),
            ("task_stop", self._on_stop),
        ]

    def _apply_translations(self) -> None:
        self._root_label.setText(_t("chatops_root_label"))
        self._cmd_label.setText(_t("chatops_cmd_label"))
        self._output_label.setText(_t("chatops_output_label"))
        self._script_root.setPlaceholderText(_t("chatops_root_placeholder"))
        self._command_input.setPlaceholderText(
            _t("chatops_cmd_placeholder"),
        )

    def _on_browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, _t("chatops_browse_btn"))
        if path:
            self._script_root.setText(path)

    def _on_send(self) -> None:
        message = self._command_input.text().strip()
        if not message:
            return
        context = {}
        root = self._script_root.text().strip()
        if root:
            context["script_root"] = root
        if not self._runs.start_script(functools.partial(_dispatch, self._router, message, context)):
            self._output.append(_t("task_busy"))
            return
        self._pending_message = message
        self._output.append(f"> {message}")

    def _on_stop(self) -> None:
        if self._runs.stop():
            self._output.append(_t("task_stopping"))

    def _show_error(self, error: object) -> None:
        if was_stopped(error):
            self._output.append(_t("task_stopped"))
            return
        self._output.append(f"router error: {error}")

    def _show_result(self, result: Any) -> None:
        if result is None:
            self._output.append(
                f"(no match for: {self._pending_message!r} — did you miss the / prefix?)",
            )
            return
        prefix = "✓" if result.succeeded else "✗"
        self._output.append(f"{prefix} {result.text}")
        if result.artifact_path:
            self._output.append(f"  artifact: {result.artifact_path}")


__all__ = ["ChatOpsTab"]
