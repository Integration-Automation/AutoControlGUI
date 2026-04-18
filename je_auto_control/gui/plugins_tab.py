"""Plugins tab: load extra AC_ commands from a user directory."""
from typing import Optional

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.plugin_loader.plugin_loader import (
    load_plugin_directory, register_plugin_commands,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class PluginsTab(TranslatableMixin, QWidget):
    """Pick a directory of plugins, register their ``AC_*`` callables."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._dir_input = QLineEdit()
        self._list = QListWidget()
        self._status_text = _t("pl_no_loaded")
        self._status = QLabel(self._status_text)
        self._status_is_translatable = True
        self._build_layout()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        form = QHBoxLayout()
        form.addWidget(self._tr(QLabel(), "pl_dir_label"))
        form.addWidget(self._dir_input, stretch=1)
        browse = self._tr(QPushButton(), "browse")
        browse.clicked.connect(self._browse)
        form.addWidget(browse)
        load = self._tr(QPushButton(), "pl_load")
        load.clicked.connect(self._on_load)
        form.addWidget(load)
        root.addLayout(form)
        root.addWidget(self._tr(QLabel(), "pl_registered_label"))
        root.addWidget(self._list, stretch=1)
        root.addWidget(self._status)

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        if self._status_is_translatable:
            self._status.setText(_t("pl_no_loaded"))

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, _t("pl_dialog_plugin_dir"))
        if path:
            self._dir_input.setText(path)

    def _on_load(self) -> None:
        path = self._dir_input.text().strip()
        if not path:
            return
        try:
            commands = load_plugin_directory(path)
        except (OSError, NotADirectoryError) as error:
            QMessageBox.warning(self, "Error", str(error))
            return
        if not commands:
            self._status.setText(f"No AC_* callables found in {path}")
            self._status_is_translatable = False
            return
        registered = register_plugin_commands(commands)
        self._list.clear()
        for name in registered:
            self._list.addItem(name)
        self._status.setText(f"Registered {len(registered)} commands from {path}")
        self._status_is_translatable = False
