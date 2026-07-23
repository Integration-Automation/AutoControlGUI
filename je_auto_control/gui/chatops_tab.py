"""Chat-Ops tab: test slash commands locally before wiring them to Slack."""
from typing import Optional

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.chatops import (
    CommandRouter, register_chatops_default_commands,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


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

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("chatops_browse_btn", self._on_browse),
            ("chatops_send_btn", self._on_send),
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
        try:
            result = self._router.dispatch(message, context=context)
        except (RuntimeError, ValueError) as error:
            self._output.append(f"router error: {error}")
            return
        if result is None:
            self._output.append(
                f"(no match for: {message!r} — did you miss the / prefix?)",
            )
            return
        prefix = "✓" if result.succeeded else "✗"
        self._output.append(f"{prefix} {result.text}")
        if result.artifact_path:
            self._output.append(f"  artifact: {result.artifact_path}")


__all__ = ["ChatOpsTab"]
