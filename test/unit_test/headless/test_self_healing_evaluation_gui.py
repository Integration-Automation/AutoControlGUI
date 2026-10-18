"""Offscreen comparison views keep worker results, cancellation and destruction safe."""
import json
from pathlib import Path
from threading import Event, get_ident
import time

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton

from je_auto_control.gui.healing_evaluation_panel import HealingEvaluationPanel
from je_auto_control.gui.healing_evaluation_worker import HealingEvaluationWorker
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.self_healing import evaluate_healing_manifest

DATASET = Path(__file__).resolve().parents[3] / "benchmarks/self_healing/dataset.json"


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(app):
    widget = HealingEvaluationPanel()
    yield widget
    widget.cancel()
    if widget._handle is not None:
        assert widget._handle.wait(5)
    widget.deleteLater()
    app.processEvents()


def until(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert predicate()


def test_panel_starts_empty_and_exposes_only_actions(panel):
    assert panel.findChildren(QPushButton) == []
    assert panel._summary.rowCount() == panel._cases.rowCount() == 0
    assert panel._handle is None
    assert len(panel.menu_actions()) == 5


def test_background_comparison_details_and_shared_exports(panel, app, tmp_path, monkeypatch):
    panel._path.setText(str(DATASET))
    panel.evaluate()
    until(app, lambda: panel._report is not None and panel._handle is None)
    assert panel._summary.rowCount() == 2 and panel._cases.rowCount() == 10
    panel._cases.setCurrentCell(0, 0)
    assert json.loads(panel._details.toPlainText())["step_id"] == "legacy-submit"
    for suffix in ("json", "html"):
        path = tmp_path / f"comparison.{suffix}"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args, **_kwargs: (str(path), ""))
        getattr(panel, "export_" + suffix)()
        assert path.is_file() and "frame_hash" in path.read_text(encoding="utf-8")


def test_changed_selection_cancels_and_discards_late_result(panel, app, monkeypatch):
    started, release = Event(), Event()
    report = evaluate_healing_manifest(DATASET)
    thread_ids = []

    def slow(*_args, **_kwargs):
        thread_ids.append(get_ident())
        started.set()
        assert release.wait(5)
        return report

    monkeypatch.setattr("je_auto_control.gui.healing_evaluation_worker.evaluate_healing_manifest", slow)
    panel._path.setText(str(DATASET))
    panel.evaluate()
    assert started.wait(5)
    panel._path.setText("different.json")
    release.set()
    until(app, lambda: panel._handle is None)
    assert panel._report is None and panel._cases.rowCount() == 0
    assert thread_ids[0] != get_ident()


def test_worker_revalidates_authority_and_pre_cancel_before_io(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("no file read permitted")

    monkeypatch.setattr("je_auto_control.gui.healing_evaluation_worker.evaluate_healing_manifest", forbidden)
    with authorization_scope(AuthorizationContext("reader", Role.VIEWER)):
        worker = HealingEvaluationWorker(1, str(DATASET))
    assert worker._evaluate().status == "error"
    worker.request_stop()
    assert worker._evaluate().status == "cancelled"
    worker.deleteLater()


def test_panel_destruction_requests_stop_without_touching_dead_widgets(app, monkeypatch):
    started, release = Event(), Event()
    report = evaluate_healing_manifest(DATASET)

    def slow(*_args, **_kwargs):
        started.set()
        assert release.wait(5)
        return report

    monkeypatch.setattr("je_auto_control.gui.healing_evaluation_worker.evaluate_healing_manifest", slow)
    widget = HealingEvaluationPanel()
    widget._path.setText(str(DATASET))
    widget.evaluate()
    assert started.wait(5)
    handle, worker = widget._handle, widget._worker
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert worker._stop.is_set()
    release.set()
    assert handle.wait(5)
    app.processEvents()
