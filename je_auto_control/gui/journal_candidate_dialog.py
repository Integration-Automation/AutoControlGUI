"""Owned modeless review dialog shared by Recording Editor and Script Builder."""
import weakref
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import QDialog, QMenuBar, QVBoxLayout, QWidget

from je_auto_control.gui.journal_candidate_panel import JournalCandidatePanel
from je_auto_control.gui.journal_candidate_worker import baseline_snapshot
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.codegen.candidate_models import CandidateGenerationError, CandidateScript
from je_auto_control.utils.rbac.policy import authorize_command


class JournalCandidateDialog(QDialog):
    """Keep review controls and Actions available without blocking the parent editor's event loop."""

    def __init__(self, parent: QWidget, baseline: str,
                    on_import: Optional[Callable[[CandidateScript], None]]) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(1100, 820)
        self._panel = JournalCandidatePanel(self, baseline=baseline, on_import=on_import)
        layout = QVBoxLayout(self)
        menu_bar = QMenuBar(self)
        self._actions_menu = menu_bar.addMenu("")
        self._actions: list[tuple[str, QAction]] = []
        for key, handler in self._panel.menu_actions():
            action = QAction(self)
            # pylint: disable-next=no-member  # reason: PySide binds the QAction signal at runtime
            action.triggered.connect(handler)
            self._actions_menu.addAction(action)
            self._actions.append((key, action))
        layout.setMenuBar(menu_bar)
        layout.addWidget(self._panel)
        reference = weakref.ref(self)

        def language_changed(_language: str) -> None:
            dialog = reference()
            if dialog is not None:
                dialog.retranslate()

        self._language_listener = language_changed
        language_wrapper.add_listener(language_changed)
        # pylint: disable-next=no-member  # reason: PySide binds the QObject signal at runtime
        self.destroyed.connect(lambda: language_wrapper.remove_listener(language_changed))
        self.retranslate()

    def retranslate(self) -> None:
        """Translate the dialog menu and nested review without restarting its task."""
        self.setWindowTitle(language_wrapper.translate("journal_candidate_title"))
        self._actions_menu.setTitle(language_wrapper.translate("journal_candidate_actions"))
        for key, action in self._actions:
            action.setText(language_wrapper.translate(key))
        self._panel.retranslate()

    # pylint: disable-next=invalid-name  # reason: Qt override
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802  # reason: Qt override
        """Cancel/discard pending work before the dialog or its owner goes away."""
        self._panel.close()
        language_wrapper.remove_listener(self._language_listener)
        super().closeEvent(event)


def show_journal_candidate(owner: QWidget, baseline: list[list[object]], *,
                             on_import: Optional[Callable[[CandidateScript], None]] = None,
                             current_actions: Optional[Callable[[], list[list[object]]]] = None
                             ) -> JournalCandidateDialog:
    """Open one owned dialog, refusing transfer if the target editor changed after its diff baseline."""
    authorize_command("AC_generate_candidate_from_log")
    dialogs: list[JournalCandidateDialog] = owner.findChildren(
        JournalCandidateDialog, options=Qt.FindChildOption.FindDirectChildrenOnly,
    )
    if dialogs:
        dialogs[0].show()
        dialogs[0].raise_()
        return dialogs[0]
    rendered, token = baseline_snapshot(baseline)

    def transfer(candidate: CandidateScript) -> None:
        authorize_command("AC_generate_candidate_from_log")
        if current_actions is None or on_import is None:
            raise CandidateGenerationError("candidate has no target editor")
        if baseline_snapshot(current_actions())[1] != token:
            raise CandidateGenerationError(language_wrapper.translate("journal_candidate_stale"))
        on_import(candidate)

    dialog = JournalCandidateDialog(owner, rendered, transfer if on_import is not None else None)
    dialog.show()
    return dialog


def close_candidate_dialogs(owner: QWidget) -> None:
    """Close only this editor's dialogs, requesting cancellation without waiting on GUI I/O."""
    for dialog in owner.findChildren(JournalCandidateDialog, options=Qt.FindChildOption.FindDirectChildrenOnly):
        dialog.close()
