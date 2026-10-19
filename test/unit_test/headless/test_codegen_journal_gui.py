"""Offscreen journal candidate review never runs imported actions."""
import time

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
from PySide6.QtWidgets import QApplication, QPushButton

from headless import test_codegen_from_journal as fixtures

journal = fixtures.journal
forbid_dispatch = fixtures.forbid_dispatch


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(app):
    from je_auto_control.gui.journal_candidate_panel import JournalCandidatePanel
    view = JournalCandidatePanel()
    yield view
    view.cancel()
    if view._handle is not None:
        view._handle.wait(5)
    view.close()
    view.deleteLater()
    app.processEvents()


def idle(app, panel):
    deadline = time.monotonic() + 5
    while panel._handle is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert panel._handle is None


def test_review_shows_code_diff_manifest_and_warnings_offscreen(journal, panel, app):
    fixtures.append_step(journal, "kept")
    panel._path.setText(str(journal.path))
    panel._run_id.setText("selected")
    panel._start_generate()
    idle(app, panel)
    assert panel._candidate is not None
    assert "def test_journal_candidate" in panel._code.toPlainText()
    assert "+" in panel._diff.toPlainText()
    assert "source_sha256" in panel._manifest.toPlainText()
    assert panel._warnings.toPlainText()
    assert not panel.findChildren(QPushButton)


def test_changing_source_clears_review_and_prevents_stale_import(journal, panel, app):
    fixtures.append_step(journal, "kept")
    panel._path.setText(str(journal.path))
    panel._run_id.setText("selected")
    panel._start_generate()
    idle(app, panel)
    panel._run_id.setText("other")
    assert panel._candidate is None and not panel._code.toPlainText()


def test_builder_import_is_explicit_and_never_dispatches(journal, app):
    from je_auto_control.gui.script_builder.builder_tab import ScriptBuilderTab
    fixtures.append_step(journal, "kept")
    builder = ScriptBuilderTab()
    from je_auto_control import generate_candidate_from_log
    candidate = generate_candidate_from_log(journal.path, run_id="selected")
    assert builder._tree.root_steps() == []
    builder._import_journal_candidate(candidate)
    from je_auto_control.gui.script_builder.step_model import steps_to_actions
    assert steps_to_actions(builder._tree.root_steps()) == candidate.actions
    assert builder._file_extras["journal_candidate"]["run_id"] == "selected"
    builder.close()
    builder.deleteLater()
    app.processEvents()


def test_import_callback_runs_only_after_explicit_review_action(journal, app):
    from je_auto_control.gui.journal_candidate_panel import JournalCandidatePanel
    received = []
    view = JournalCandidatePanel(on_import=lambda candidate: received.append(candidate.actions))
    fixtures.append_step(journal, "kept")
    view._path.setText(str(journal.path))
    view._run_id.setText("selected")
    view._start_generate()
    idle(app, view)
    assert received == []
    view._import_candidate()
    idle(app, view)
    assert received == [[["AC_sleep", {"seconds": 0}]]]
    assert view._status_key == "imported"
    view.close()
    view.deleteLater()
    app.processEvents()


def test_builder_edits_after_baseline_are_not_overwritten(journal, app):
    from je_auto_control.gui.journal_candidate_dialog import show_journal_candidate
    from je_auto_control.gui.script_builder.builder_tab import ScriptBuilderTab
    from je_auto_control.gui.script_builder.step_model import Step, steps_to_actions
    builder = ScriptBuilderTab()
    dialog = show_journal_candidate(builder, [], on_import=builder._import_journal_candidate,
                                      current_actions=lambda: steps_to_actions(builder._tree.root_steps()))
    view = dialog._panel
    fixtures.append_step(journal, "kept")
    view._path.setText(str(journal.path))
    view._run_id.setText("selected")
    view._start_generate()
    idle(app, view)
    builder._tree.add_step(Step("AC_sleep", {"seconds": 19}))
    view._import_candidate()
    idle(app, view)
    assert steps_to_actions(builder._tree.root_steps()) == [["AC_sleep", {"seconds": 19}]]
    assert view._status_key == "error"
    builder.close()
    builder.deleteLater()
    app.processEvents()


def test_viewer_worker_cannot_open_source_after_leaving_registration_scope(app, monkeypatch):
    from je_auto_control.gui.journal_candidate_worker import JournalCandidateTask, JournalCandidateWorker
    from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope

    def forbidden(*_args, **_kwargs):
        pytest.fail("viewer must be rejected before journal I/O")

    monkeypatch.setattr("je_auto_control.gui.journal_candidate_worker.generate_candidate_from_log", forbidden)
    with authorization_scope(AuthorizationContext("viewer", Role.VIEWER)):
        worker = JournalCandidateWorker(JournalCandidateTask(1, "generate", "private.jsonl", "selected"))
    outcomes = []
    worker.finished.connect(outcomes.append)
    worker.run()
    assert outcomes[0].status == "error" and outcomes[0].candidate is None
    worker.deleteLater()
    app.processEvents()


def test_completed_export_is_not_relabelled_cancelled(journal, app, tmp_path, monkeypatch):
    from je_auto_control import generate_candidate_from_log
    from je_auto_control.gui import journal_candidate_worker as module
    fixtures.append_step(journal, "kept")
    candidate = generate_candidate_from_log(journal.path, run_id="selected")
    output = tmp_path / "review.zip"
    worker = module.JournalCandidateWorker(module.JournalCandidateTask(
        1, "export", str(output), candidate=candidate,
    ))
    write = module.write_candidate_archive

    def export(*args, **kwargs):
        result = write(*args, **kwargs)
        worker.request_stop()
        return result

    monkeypatch.setattr(module, "write_candidate_archive", export)
    outcomes = []
    worker.finished.connect(outcomes.append)
    worker.run()
    assert outcomes[0].status == "ok" and output.exists()
    worker.deleteLater()
    app.processEvents()


def test_close_cancels_generation_and_discards_late_result(journal, panel, app, monkeypatch):
    import threading
    from je_auto_control.gui import journal_candidate_worker as module
    fixtures.append_step(journal, "kept")
    original = module.generate_candidate_from_log
    entered, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "generate_candidate_from_log", blocked)
    panel._path.setText(str(journal.path))
    panel._run_id.setText("selected")
    panel._start_generate()
    try:
        assert entered.wait(2)
        panel.close()
    finally:
        release.set()
    idle(app, panel)
    assert panel._candidate is None and not panel._code.toPlainText()


def test_owned_dialog_retranslates_and_releases_language_listener(app):
    from PySide6.QtWidgets import QWidget
    from je_auto_control.gui.journal_candidate_dialog import show_journal_candidate
    from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
    owner = QWidget()
    before = len(language_wrapper._listeners)
    dialog = show_journal_candidate(owner, [])
    previous = language_wrapper.language
    try:
        language_wrapper.reset_language("Traditional_Chinese")
        assert "日誌" in dialog.windowTitle()
        assert len(language_wrapper._listeners) == before + 1
        dialog.close()
        app.processEvents()
        assert len(language_wrapper._listeners) == before
    finally:
        language_wrapper.reset_language(previous)
        owner.close()
        owner.deleteLater()
        app.processEvents()
