"""Composite widget that ties the step tree and form into a Script Builder tab.

Run executes the steps off the GUI thread as a stoppable executor run, one at
a time; Stop ends it at its next checkpoint.

Every secret-named field of a result (a freshly issued token, at any depth,
whatever the command) is masked in the result pane. The run reports each
command's result -- the ones inside a block too -- to a
:class:`OneTimeCollector`, which keeps what the pane masks, in memory. The
"one-time values" button hands those values to :class:`OneTimeValueDialog` --
once: the tab forgets them as it opens the dialog, when the next run starts
and when it is disposed. A run that was stopped or failed still offers what
it had issued by then.
"""
import functools
import json
from typing import List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QMenu, QMessageBox, QPushButton, QSplitter,
    QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from je_auto_control.gui._dispose import release_resources
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._journal_import import candidate_summary, pick_journal_candidate
from je_auto_control.gui._tab_task import TabTask, was_stopped
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.gui.script_builder.command_schema import (
    CATEGORIES, COMMAND_SPECS, specs_in_category,
)
from je_auto_control.gui.script_builder.one_time_dialog import OneTimeValueDialog
from je_auto_control.gui.script_builder.step_form_view import StepFormView
from je_auto_control.gui.script_builder.step_list_view import StepTreeView
from je_auto_control.gui.script_builder.step_model import (
    OneTimeCollector, OneTimeValue, Step, actions_to_steps, displayable_record,
    load_action_file, save_action_file, steps_to_actions,
)
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_executor import execute_action


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def _run_actions(actions: list, collector: OneTimeCollector) -> object:
    """Worker thread: execute the built action list, reporting each result to ``collector``."""
    return execute_action(actions, result_callback=collector.note)


class ScriptBuilderTab(TranslatableMixin, QWidget):
    """Visual editor for composing AC_* scripts."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._tree = StepTreeView()
        self._form = StepFormView()
        self._result = QTextEdit()
        self._result.setReadOnly(True)
        self._result.setMaximumHeight(140)
        self._add_btn: Optional[QToolButton] = None
        # The other top-level keys of a loaded {"auto_control": [...]} file,
        # written back on Save; None for a bare list.
        self._file_extras: Optional[dict] = None
        # The secrets of the last run, until they are revealed or the next run starts.
        self._one_time: List[OneTimeValue] = []
        # What the running (or last) run reported; emptied when its values are claimed.
        self._collector: Optional[OneTimeCollector] = None
        # The line of the result pane that says values are waiting, to replace once they are shown.
        self._available_line = ""
        self._reveal_btn = QPushButton()
        self._reveal_dialog: Optional[OneTimeValueDialog] = None
        self._runs = TabTask(self)
        self._runs.result.connect(self._show_run_result)
        self._runs.error.connect(self._show_run_error)
        self._build_layout()
        self._wire_signals()

    def dispose(self) -> None:
        """Release what the tab holds beyond its widgets: the command still running in the background.

        A script run is stopped; other work cannot be interrupted, so it runs to its end and its
        result is dropped. Called by ``close_tab(key, release=True)``; safe to call twice.
        """
        release_resources(self, self._forget_one_time)

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        if self._add_btn is not None:
            self._add_btn.setText(_t("sb_add_step"))
        if hasattr(self._form, "retranslate"):
            self._form.retranslate()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.addLayout(self._build_toolbar())
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._form)
        splitter.setSizes([320, 480])
        root.addWidget(splitter, stretch=1)
        root.addWidget(self._result)

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(self._add_button())
        for key, handler in (
            ("sb_delete", self._on_delete),
            ("sb_up", lambda: self._tree.move_selected(-1)),
            ("sb_down", lambda: self._tree.move_selected(1)),
        ):
            btn = self._tr(QPushButton(), key)
            btn.clicked.connect(handler)
            bar.addWidget(btn)
        bar.addStretch()
        for key, handler in (
            ("sb_load_json", self._on_load),
            ("sb_import_journal", self._on_import_journal),
            ("sb_save_json", self._on_save),
            ("sb_run", self._on_run),
            ("task_stop", self._on_stop),
        ):
            btn = self._tr(QPushButton(), key)
            btn.clicked.connect(handler)
            bar.addWidget(btn)
        self._tr(self._reveal_btn, "sb_one_time_show")
        self._reveal_btn.setEnabled(False)
        self._reveal_btn.clicked.connect(self._on_reveal)
        bar.addWidget(self._reveal_btn)
        return bar

    def _add_button(self) -> QToolButton:
        button = QToolButton()
        button.setText(_t("sb_add_step"))
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        for category in CATEGORIES:
            submenu = menu.addMenu(category)
            for spec in specs_in_category(category):
                action = QAction(spec.label, submenu)
                action.triggered.connect(
                    lambda _checked=False, cmd=spec.command: self._add_step_from_command(cmd)
                )
                submenu.addAction(action)
        button.setMenu(menu)
        self._add_btn = button
        return button

    def _wire_signals(self) -> None:
        self._tree.selected_step_changed.connect(self._form.load_step)
        self._form.step_changed.connect(self._tree.refresh_current_label)

    def _add_step_from_command(self, command: str) -> None:
        spec = COMMAND_SPECS.get(command)
        if spec is None:
            return
        defaults = {
            f.name: f.default for f in spec.fields
            if f.default is not None and not f.optional
        }
        step = Step(command=command, params=defaults)
        self._tree.add_step(step)

    def _on_delete(self) -> None:
        self._tree.remove_selected()
        self._form.load_step(None)

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, _t("sb_dialog_save"), "", "JSON (*.json)",
        )
        if not path:
            return
        try:
            save_action_file(path, self._tree.root_steps(), self._file_extras)
            self._result.setPlainText(f"Saved: {path}")
        except (AutoControlException, OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("sb_dialog_load"), "", "JSON (*.json)",
        )
        if not path:
            return
        try:
            steps, self._file_extras = load_action_file(path)
            self._tree.load_steps(steps)
            self._form.load_step(None)
            self._result.setPlainText(f"Loaded: {path}")
        except (AutoControlException, OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _on_import_journal(self) -> None:
        """Load the candidate built from an action journal run as steps to review."""
        candidate = pick_journal_candidate(self)
        if candidate is None:
            return
        try:
            steps = actions_to_steps(candidate.actions)
        except (AutoControlException, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Error", str(error))
            return
        self._file_extras = None
        self._tree.load_steps(steps)
        self._form.load_step(None)
        self._result.setPlainText("\n".join((
            f"Imported journal run {candidate.manifest['run_id']}: {len(steps)} step(s)",
            candidate_summary(candidate))))

    def _on_run(self) -> None:
        try:
            actions = steps_to_actions(self._tree.root_steps())
        except (AutoControlException, OSError, ValueError, TypeError,
                RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))
            return
        if not actions:
            QMessageBox.information(self, "Info", "No steps to run")
            return
        collector = OneTimeCollector()
        if not self._runs.start_script(functools.partial(_run_actions, actions, collector)):
            self._result.setPlainText(_t("task_busy"))
            return
        self._forget_one_time()
        self._collector = collector
        self._result.setPlainText(_t("task_running"))

    def _on_stop(self) -> None:
        if self._runs.stop():
            self._result.setPlainText(_t("task_stopping"))

    def _show_run_result(self, result: object) -> None:
        # Masked first: a result may carry a token (AC_user_add, AC_jwt_encode, a lease...).
        self._show_with_one_time(
            [json.dumps(displayable_record(result), indent=2, default=str, ensure_ascii=False)])

    def _show_with_one_time(self, lines: Sequence[str]) -> None:
        """Fill the result pane with ``lines`` and say what the ended run left to reveal."""
        shown = [line for line in lines if line]
        collector, self._collector = self._collector, None
        self._one_time, truncated = collector.take() if collector is not None else ([], False)
        self._available_line = ""
        if self._one_time:
            self._available_line = _t("sb_one_time_available").format(count=len(self._one_time))
            shown.append(self._available_line)
        if truncated and collector is not None:
            shown.append(_t("sb_one_time_limit").format(limit=collector.limit))
        self._result.setPlainText("\n\n".join(shown))
        self._reveal_btn.setEnabled(bool(self._one_time))

    def _forget_one_time(self) -> None:
        """Drop the last run's secrets and close the dialog still showing them."""
        self._one_time = []
        self._collector = None
        self._available_line = ""
        self._reveal_btn.setEnabled(False)
        dialog, self._reveal_dialog = self._reveal_dialog, None
        if dialog is not None:
            dialog.forget()
            dialog.done(0)  # emits ``finished`` even when it was never shown

    def _take_one_time_dialog(self) -> Optional[OneTimeValueDialog]:
        """Build the reveal dialog for the pending values and forget them here; not shown yet."""
        if not self._one_time:
            return None
        values, self._one_time = self._one_time, []
        self._reveal_btn.setEnabled(False)
        self._mark_one_time_shown()
        dialog = OneTimeValueDialog(values, self)
        dialog.finished.connect(dialog.deleteLater)
        dialog.finished.connect(self._on_reveal_closed)
        self._reveal_dialog = dialog
        return dialog

    def _mark_one_time_shown(self) -> None:
        """Replace the pane's "values are available" line: they were shown and are gone."""
        line, self._available_line = self._available_line, ""
        text = self._result.toPlainText()
        if line and line in text:
            self._result.setPlainText(text.replace(line, _t("sb_one_time_shown")))

    def _on_reveal(self) -> None:
        dialog = self._take_one_time_dialog()
        if dialog is not None:
            dialog.open()  # window-modal without a nested event loop

    def _on_reveal_closed(self, _result: int = 0) -> None:
        self._reveal_dialog = None

    def _show_run_error(self, error: object) -> None:
        # A token issued before the stop or the failure exists; it is still offered.
        if was_stopped(error):
            self._show_with_one_time([_t("task_stopped")])
            return
        self._show_with_one_time([])
        QMessageBox.warning(self, "Error", str(error))
