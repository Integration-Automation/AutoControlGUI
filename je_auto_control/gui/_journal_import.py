"""Shared dialog flow: pick an action journal run and build its candidate script.

The tabs that open a candidate (Run History, Recording Editor, Script Builder)
only differ in what they do with it; choosing the file and the run, building
the candidate and showing its warnings is the same everywhere. All logic stays
in ``utils/codegen/journal_import`` -- nothing here is unreachable headlessly.

A candidate that would replace something -- the recording open in the editor,
a script exported earlier -- is shown as a diff first
(:func:`confirm_candidate_diff`); the diff itself comes from
``utils/codegen/candidate_diff``, the same one ``AC_generate_code_from_journal``
returns for ``diff_against``.
"""
import html
from typing import Optional

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QInputDialog, QLabel, QMessageBox, QTextEdit,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.action_journal.store import list_journal_runs
from je_auto_control.utils.codegen.candidate_diff import CandidateDiff
from je_auto_control.utils.codegen.journal_import import (
    CandidateScript, generate_candidate_from_log,
)
from je_auto_control.utils.exception.exceptions import AutoControlException

JOURNAL_FILTER = "Journal (*.jsonl);;All files (*)"


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def _pick_run(parent: QWidget, path: str) -> Optional[str]:
    """The run to import: the only one, or the one the user chooses."""
    runs = [run["run_id"] for run in list_journal_runs(path)]
    if not runs:
        QMessageBox.information(parent, _t("jr_dialog_open"), _t("jr_no_runs"))
        return None
    if len(runs) == 1:
        return runs[0]
    # Newest first: the run just recorded is the one usually wanted.
    run_id, accepted = QInputDialog.getItem(
        parent, _t("jr_dialog_open"), _t("jr_pick_run"), runs[::-1], 0, False)
    return run_id if accepted else None


#: Colours for added / removed / hunk-header lines; readable on the dark and the light theme.
_DIFF_COLOURS = {"+": "#2e9e4f", "-": "#d9534f", "@": "#5b9dff"}


def diff_as_html(diff: CandidateDiff) -> str:
    """The unified diff as HTML: one escaped line per row, added / removed / hunk lines coloured."""
    rows = []
    for index, line in enumerate(diff.text.splitlines()):
        text = html.escape(line) or "&nbsp;"
        colour = None if index < 2 else _DIFF_COLOURS.get(line[:1])     # the first two rows are file headers
        rows.append(f'<span style="color:{colour}">{text}</span>' if colour else text)
    return "<pre>" + "\n".join(rows) + "</pre>"


def diff_summary(diff: CandidateDiff) -> str:
    """One line saying how much the candidate changes."""
    if diff.identical:
        return _t("jr_diff_identical")
    return _t("jr_diff_summary").replace("{added}", str(diff.added)).replace("{removed}", str(diff.removed))


class CandidateDiffDialog(QDialog):
    """Shows what a candidate would change; accepting it means "replace"."""

    def __init__(self, diff: CandidateDiff, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_t("jr_diff_title"))
        self.resize(820, 560)
        layout = QVBoxLayout(self)
        self.summary = QLabel(diff_summary(diff))
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.view.setHtml(diff_as_html(diff))
        layout.addWidget(self.view, stretch=1)
        self.buttons = QDialogButtonBox()
        replace = self.buttons.addButton(_t("jr_diff_replace"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.addButton(_t("jr_diff_keep"), QDialogButtonBox.ButtonRole.RejectRole)
        replace.setEnabled(not diff.identical)      # nothing to replace with
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)


def confirm_candidate_diff(parent: QWidget, diff: CandidateDiff) -> bool:
    """Show ``diff`` and return whether the user chose to replace what is there."""
    dialog = CandidateDiffDialog(diff, parent)
    try:
        return dialog.exec() == QDialog.DialogCode.Accepted
    finally:
        dialog.deleteLater()


def candidate_summary(candidate: CandidateScript) -> str:
    """The candidate's caveats as text: the observed-path notice, then warnings."""
    lines = [_t("jr_observed_only")] if candidate.observed_path_only else []
    lines.extend(candidate.warnings)
    return "\n".join(lines)


def pick_journal_candidate(parent: QWidget, target: str = "pytest"
                           ) -> Optional[CandidateScript]:
    """Ask for a journal file and run, build the candidate, show what to check.

    Returns ``None`` when the user cancels or the journal cannot be used (the
    reason is shown). The candidate is built and dry-run only, never executed.
    """
    path, _ = QFileDialog.getOpenFileName(
        parent, _t("jr_dialog_open"), "", JOURNAL_FILTER)
    if not path:
        return None
    try:
        run_id = _pick_run(parent, path)
        if run_id is None:
            return None
        candidate = generate_candidate_from_log(path, run_id=run_id, target=target)
    except (AutoControlException, OSError, ValueError) as error:
        QMessageBox.warning(parent, _t("jr_dialog_open"), str(error))
        return None
    summary = candidate_summary(candidate)
    if summary:
        QMessageBox.information(parent, _t("jr_dialog_open"), summary)
    return candidate
