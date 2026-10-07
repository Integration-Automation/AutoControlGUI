"""Translated selected-feature dependency recovery with native selectable text."""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper


class DependencyPanel(QWidget):
    """Retain the dependency reason while language changes refresh the recovery labels."""

    def __init__(self, reason: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._reason = reason
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addStretch()
        self.setProperty('capability_reason', reason)
        self.retranslate()

    def retranslate(self) -> None:
        """Translate recovery text without discarding the original import failure."""
        self._label.setText(language_wrapper.translate('feature_dependency_unavailable') + '\n\n' +
                            language_wrapper.translate('feature_dependency_recovery') + '\n\n' +
                            'Remote Desktop: python -m pip install je_auto_control[webrtc]\n' + self._reason)
