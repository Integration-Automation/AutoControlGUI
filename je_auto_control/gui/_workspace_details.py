"""Read-only workflow state, recovery and progress display for the workspace chrome."""
from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QProgressBar, QVBoxLayout, QWidget

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.tab_registry import TabRegistryError

_STATES = frozenset(('empty', 'ready', 'busy', 'error', 'needs_permission', 'needs_dependency', 'unsupported'))


class WorkspaceDetails(QWidget):  # pylint: disable=too-many-instance-attributes  # reason: widgets plus distinct state/reason/recovery/progress data
    """Present shared states without claiming that workspace readiness is native permission."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(210)
        self.setProperty('role', 'surface')
        self.state = 'empty'
        self._reason = ''
        self._recovery = ''
        self._active = ''
        self._actions: tuple[str, ...] = ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self._heading = QLabel()
        self._heading.setProperty('role', 'heading')
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._workflow = QLabel()
        self._workflow.setWordWrap(True)
        self.reason = QPlainTextEdit()
        self.reason.setReadOnly(True)
        self.reason.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self._progress = QProgressBar()
        for widget in (self._heading, self._status, self._workflow, self.reason, self._progress):
            layout.addWidget(widget)
        self.retranslate()

    def set_workflow(self, title: str, actions: tuple[str, ...]) -> None:
        """Show available Actions menu labels; this view never executes them."""
        self._active, self._actions = title, actions
        self.retranslate()

    def set_state(self, state: str, reason: str = '', recovery: str = '',
                  progress: Optional[int] = None) -> None:
        """Display explicit empty/error/permission/dependency states and bounded progress."""
        if state not in _STATES or not isinstance(reason, str) or not isinstance(recovery, str):
            raise TabRegistryError('unknown workspace state or invalid reason/recovery')
        if progress is not None and (isinstance(progress, bool) or not isinstance(progress, int)
                                     or not 0 <= progress <= 100):
            raise TabRegistryError('workspace progress must be an integer from 0 through 100')
        self.state, self._reason, self._recovery = state, reason, recovery
        self._progress.setVisible(state == 'busy')
        self._progress.setRange(0, 0 if progress is None else 100)
        if progress is not None:
            self._progress.setValue(progress)
        self.retranslate()

    def retranslate(self) -> None:
        """Keep state/recovery data while refreshing labels and available action descriptions."""
        self._heading.setText(language_wrapper.translate('workspace_details'))
        self._status.setText(language_wrapper.translate('workspace_state_' + self.state))
        self._status.setProperty('role', 'error' if self.state == 'error' else 'muted')
        self._workflow.setText(self._active)
        content = [language_wrapper.translate('workspace_state_hint_' + self.state)]
        if self._reason:
            content.append(self._reason)
        if self._recovery:
            content.extend([language_wrapper.translate('workspace_recovery'), self._recovery])
        if self._actions:
            content.extend([language_wrapper.translate('workspace_actions_hint'),
                            *('• ' + language_wrapper.translate(key, key) for key in self._actions)])
        self.reason.setPlainText('\n\n'.join(content))
