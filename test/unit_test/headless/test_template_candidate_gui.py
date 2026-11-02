"""Candidate review and atomic transitions remain responsive and context-bound offscreen."""
import time

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
from PySide6.QtWidgets import QApplication, QPushButton

from headless import test_template_candidates as candidate_fixtures
from je_auto_control.gui.template_candidate_panel import TemplateCandidatePanel
from je_auto_control.gui.template_candidate_worker import TemplateCandidateRequest, TemplateCandidateWorker
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope

FIXTURES = candidate_fixtures.FIXTURES
no_device_or_backend = candidate_fixtures.no_device_or_backend
revision_files = candidate_fixtures.revision_files
create = candidate_fixtures.create


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(app):
    view = TemplateCandidatePanel()
    yield view
    view.cancel()
    if view._handle is not None:
        view._handle.wait(5)
    view.deleteLater()
    app.processEvents()


def until_idle(app, panel):
    deadline = time.monotonic() + 5
    while panel._handle is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert panel._handle is None


def test_actions_complete_preview_verify_accept_and_revert(panel, app, revision_files):
    target, bundle, dataset = revision_files
    original = target.read_bytes()
    panel._template.setText(str(target))
    panel._candidate.setText(str(FIXTURES / "new.png"))
    panel._bundle.setText(str(bundle))
    panel._dataset.setText(str(dataset))
    panel._threshold.setValue(0.99)
    panel._start("create")
    until_idle(app, panel)
    assert panel._status_key == "created" and target.read_bytes() == original
    assert not panel._revision.text()
    panel._start("preview")
    until_idle(app, panel)
    assert len(panel._revision.text()) == 64
    assert not panel._original.pixmap().isNull() and not panel._replacement.pixmap().isNull()
    panel._start("verify")
    until_idle(app, panel)
    assert panel._status_key == "eligible" and target.read_bytes() == original
    panel._start("accept")
    until_idle(app, panel)
    assert panel._status_key == "done" and target.read_bytes() != original
    panel._start("revert")
    until_idle(app, panel)
    assert target.read_bytes() == original
    assert panel.findChildren(QPushButton) == []


def test_preview_is_required_before_gui_acceptance(panel):
    panel._start("accept")
    assert panel._handle is None and panel._status_key == "review_required"


def test_new_bundle_selection_discards_previous_review(panel, app, revision_files):
    _, bundle, _ = revision_files
    create(revision_files)
    panel._bundle.setText(str(bundle))
    panel._start("preview")
    until_idle(app, panel)
    assert panel._revision.text()
    panel._bundle.setText("different.json")
    assert not panel._revision.text() and not panel._details.toPlainText()
    panel._start("accept")
    assert panel._status_key == "review_required"


def test_deferred_worker_retains_viewer_authority(app, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("viewer must not read a candidate bundle")

    monkeypatch.setattr("je_auto_control.gui.template_candidate_worker.preview_template_candidate", forbidden)
    request = TemplateCandidateRequest(1, "preview", "", "", "private.json", "", "", 0.9)
    with authorization_scope(AuthorizationContext("viewer", Role.VIEWER)):
        worker = TemplateCandidateWorker(request)
    outcomes = []
    worker.finished.connect(outcomes.append)
    worker.run()
    assert outcomes[0].status == "error" and outcomes[0].data is None
    worker.deleteLater()


def test_committed_acceptance_is_not_relabelled_cancelled(app, monkeypatch, revision_files):
    from je_auto_control.utils.self_healing.template_candidates import accept_template_candidate
    target, bundle, dataset = revision_files
    state = create(revision_files)
    request = TemplateCandidateRequest(1, "accept", "", "", str(bundle), str(dataset), state.revision, 0.9)
    worker = TemplateCandidateWorker(request)

    def committed(*args, **kwargs):
        result = accept_template_candidate(*args, **kwargs)
        worker.request_stop()
        return result

    monkeypatch.setattr("je_auto_control.gui.template_candidate_worker.accept_template_candidate", committed)
    outcomes = []
    worker.finished.connect(outcomes.append)
    worker.run()
    assert outcomes[0].status == "ok" and outcomes[0].data["changed"] is True
    assert target.read_bytes() == (FIXTURES / "new.png").read_bytes()
    worker.deleteLater()


def test_close_cancels_active_read_and_discards_late_result(panel, app, monkeypatch, revision_files):
    import threading
    from je_auto_control.utils.self_healing.template_candidates import verify_template_candidate
    _, bundle, dataset = revision_files
    create(revision_files)
    entered, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("controlled verification was not released")
        return verify_template_candidate(*args, **kwargs)

    monkeypatch.setattr("je_auto_control.gui.template_candidate_worker.verify_template_candidate", blocked)
    panel._bundle.setText(str(bundle))
    panel._dataset.setText(str(dataset))
    try:
        panel._start("verify")
        assert entered.wait(2)
        panel.close()
    finally:
        release.set()
    until_idle(app, panel)
    assert panel._details.toPlainText() == "" and panel._status_key != "eligible"
