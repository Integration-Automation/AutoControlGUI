"""Offscreen live locator inputs and evidence browsing without native capture/input."""
import json

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
from PySide6.QtWidgets import QApplication, QPushButton

from je_auto_control.gui.self_healing_tab import SelfHealingTab
from je_auto_control.utils.self_healing import HealEvent, HealEventLog, HealOutcome


@pytest.fixture
def widget(monkeypatch, tmp_path):
    def forbidden(*_a, **_k):
        pytest.fail("offscreen GUI tests must not capture or issue native input")

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame._load_image_grab", forbidden)
    monkeypatch.setattr("je_auto_control.utils.cv2_utils.region_capture.grab_screen_region", forbidden)
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", forbidden)
    app = QApplication.instance() or QApplication([])
    log = HealEventLog(tmp_path / "events.jsonl")
    monkeypatch.setattr("je_auto_control.gui.self_healing_tab.default_heal_log", log)
    view = SelfHealingTab()
    yield view, log
    view._source.cancel()
    if view._source._handle is not None:
        view._source._handle.wait(5)
    view.deleteLater()
    app.processEvents()


def test_runtime_region_reaches_headless_api_and_comparison_stays_separate(widget, monkeypatch):
    view, _log = widget
    calls = []

    def locate(**arguments):
        calls.append(arguments)
        return HealOutcome(True, (-10, -20), "vlm")

    monkeypatch.setattr("je_auto_control.gui.self_healing_tab.self_heal_locate", locate)
    view._description_input.setText("submit")
    view._region_input.setText("[-20,-30,10,20]")
    view._on_locate()
    assert calls[0]["screen_region"] == [-20, -30, 10, 20]
    assert view.findChildren(QPushButton) == []
    assert view._group_box.parentWidget() is view._views.widget(0)
    assert view._evaluation is view._views.widget(1)


@pytest.mark.parametrize("raw", ["not-json", '"not-a-region"'])
def test_invalid_region_text_does_not_run(widget, monkeypatch, raw):
    view, _log = widget
    monkeypatch.setattr("je_auto_control.gui.self_healing_tab.self_heal_locate",
                        lambda **_kwargs: pytest.fail("invalid input must not run"))
    view._description_input.setText("submit")
    view._region_input.setText(raw)
    view._on_locate()
    assert view._status.text()


def test_selected_log_shows_version_frame_and_unknown_verification(widget):
    view, log = widget
    log.append(HealEvent("now", "image", [1, 2], 1.0, schema_version=2, locator_version="revision",
                         frame_hash="frame-hash", operation="click", operation_status="issued"))
    view.refresh_log()
    view._table.setCurrentCell(0, 0)
    details = json.loads(view._details.toPlainText())
    assert details["locator_version"] == "revision" and details["frame_hash"] == "frame-hash"
    assert details["operation_status"] == "issued" and details["verified"] is None
    log.clear()
    view.refresh_log()
    assert view._details.toPlainText() == ""


@pytest.mark.parametrize("command", ["AC_self_heal_locate", "AC_self_heal_click"])
def test_builder_edits_structured_region_without_turning_it_into_text(widget, command):
    from je_auto_control.gui.script_builder.step_form_view import StepFormView
    from je_auto_control.gui.script_builder.step_model import Step

    step = Step(command, {"description": "submit", "screen_region": [-20, -30, 10, 20]})
    form = StepFormView()
    try:
        form.load_step(step)
        field = form._editors["screen_region"]
        field.setText("[-10,-20,20,30]")
        assert step.params["screen_region"] == [-10, -20, 20, 30]
        field.setText("not-json")
        assert step.params["screen_region"] == [-10, -20, 20, 30]
    finally:
        form.deleteLater()


@pytest.mark.parametrize("verdict", [True, False])
def test_verification_input_is_explicit_and_reports_its_result(widget, monkeypatch, verdict):
    from je_auto_control import SelfHealRunResult
    from je_auto_control.gui.self_healing_tab import _t
    view, _ = widget
    calls = []

    def run(request):
        calls.append(request)
        return SelfHealRunResult(HealOutcome(True, (2, 3), "image"),
                                 "verified" if verdict else "verification_failed", verdict)

    monkeypatch.setattr("je_auto_control.gui.self_healing_tab.self_heal_run", run)
    view._description_input.setText("submit")
    view._verification_input.setText("confirmation is visible")
    view._on_locate()
    assert calls == []
    view._on_click()
    assert len(calls) == 1 and calls[0].operation == "click"
    assert calls[0].verification.description == "confirmation is visible"
    key = "self_heal_verification_passed" if verdict else "self_heal_verification_failed"
    assert view._status.text() == _t(key)
    assert view._verification_input.placeholderText()


def test_builder_roundtrips_nested_verification_request(widget):
    from je_auto_control.gui.script_builder.step_form_view import StepFormView
    from je_auto_control.gui.script_builder.step_model import Step

    options = {"operation": "click", "description": "submit", "verification": {"description": "done"}}
    step = Step("AC_self_heal_run", {"request": options})
    form = StepFormView()
    try:
        form.load_step(step)
        field = form._editors["request"]
        field.setText(json.dumps({**options, "verification": {"description": "cart is empty"}}))
        assert step.params["request"]["verification"]["description"] == "cart is empty"
        field.setText("invalid-json")
        assert step.params["request"]["operation"] == "click"
    finally:
        form.deleteLater()


def test_source_action_without_captured_metadata_does_not_read(widget, monkeypatch):
    view, log = widget
    log.append(HealEvent("now", "image", [1, 2], 1))
    view.refresh_log()
    view._table.setCurrentCell(0, 0)
    monkeypatch.setattr(view._source, "read", lambda: pytest.fail("legacy data must not invent a source"))
    view._on_source()
    assert view._views.currentWidget() is not view._source


def test_source_action_reads_only_selected_original_step_off_thread(widget, monkeypatch, tmp_path):
    import time
    import threading
    import je_auto_control as ac
    view, log = widget
    path = tmp_path / "source.jsonl"
    ac.execute_journal_run([["AC_set_var", {"name": "one", "value": 1}],
                            ["AC_set_var", {"name": "two", "value": 2}]],
                           path, options=ac.JournalRunOptions(run_id="chosen"))
    source = ac.read_events(path)[-1]
    log.append(HealEvent("now", "image", [1, 2], 1, journal_path=str(path),
                         run_id=source.run_id, step_id=source.step_id))
    view.refresh_log()
    view._table.setCurrentCell(0, 0)
    from je_auto_control.utils.action_journal.inspection import inspect_journal
    threads = []

    def inspect(*args, **kwargs):
        threads.append(threading.get_ident())
        return inspect_journal(*args, **kwargs)

    monkeypatch.setattr("je_auto_control.gui.journal_browser_worker.inspect_journal", inspect)
    view._on_source()
    app = QApplication.instance()
    deadline = time.monotonic() + 5
    while view._source._handle is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert view._source._handle is None
    assert view._views.currentWidget() is view._source
    assert view._source._step_source
    view._source.retranslate()
    from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
    assert view._source._links.currentText() == language_wrapper.translate("journal_links_step")
    assert len(view._source._events) == 2
    assert all(row["step_id"] == source.step_id for row in view._source._events)
    assert threads and threads[0] != threading.get_ident()
    view._table.clearSelection()
    assert not view._source._events


def test_source_action_switching_during_read_loads_new_target(widget, monkeypatch):
    import threading
    import time
    view, log = widget
    for step in ("first", "second"):
        log.append(HealEvent("now", "image", [1, 2], 1, journal_path=f"{step}.jsonl", run_id="run", step_id=step))
    view.refresh_log()
    entered, release = threading.Event(), threading.Event()
    calls = []

    def inspect(_path, **kwargs):
        step = kwargs["step_id"]
        calls.append(step)
        if step == "first":
            entered.set()
            if not release.wait(5):
                raise RuntimeError("controlled reader was not released")
        return [{"step_id": step, "run_id": "run", "command": "synthetic", "status": "ok", "sequence": 1}]

    monkeypatch.setattr("je_auto_control.gui.journal_browser_worker.inspect_journal", inspect)
    try:
        view._table.setCurrentCell(0, 0)
        view._on_source()
        assert entered.wait(2)
        view._table.setCurrentCell(1, 0)
        view._on_source()
    finally:
        release.set()
    app = QApplication.instance()
    deadline = time.monotonic() + 5
    while view._source._handle is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert view._source._handle is None
    assert calls == ["first", "second"]
    assert [row["step_id"] for row in view._source._events] == ["second"]
