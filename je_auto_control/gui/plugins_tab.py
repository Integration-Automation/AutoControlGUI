"""Plugins tab: load extra AC_ commands from a user directory."""
from typing import Optional

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from je_auto_control.utils.plugin_loader.plugin_loader import (
    load_plugin_directory, register_plugin_commands,
)


class PluginsTab(QWidget):
    """Pick a directory of plugins, register their ``AC_*`` callables."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._dir_input = QLineEdit()
        self._list = QListWidget()
        self._status = QLabel("No plugins loaded")
        self._build_layout()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        form = QHBoxLayout()
        form.addWidget(QLabel("Plugin dir:"))
        form.addWidget(self._dir_input, stretch=1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        form.addWidget(browse)
        load = QPushButton("Load + register")
        load.clicked.connect(self._on_load)
        form.addWidget(load)
        root.addLayout(form)
        root.addWidget(QLabel("Registered commands:"))
        root.addWidget(self._list, stretch=1)
        root.addWidget(self._status)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Plugin directory")
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
            return
        registered = register_plugin_commands(commands)
        self._list.clear()
        for name in registered:
            self._list.addItem(name)
        self._status.setText(f"Registered {len(registered)} commands from {path}")
