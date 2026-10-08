"""Shared dialog flow: pick an action journal run and build its candidate script.

The tabs that open a candidate (Run History, Recording Editor, Script Builder)
only differ in what they do with it; choosing the file and the run, building
the candidate and showing its warnings is the same everywhere. All logic stays
in ``utils/codegen/journal_import`` -- nothing here is unreachable headlessly.
"""
from typing import Optional

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QWidget

from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.action_journal.store import list_journal_runs
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
