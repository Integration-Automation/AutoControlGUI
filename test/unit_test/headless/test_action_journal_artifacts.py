"""Journal events name what a step left behind: files, reports, trace ids.

Fake commands on a private :class:`Executor`; nothing touches a real screen.
"""
import json

import pytest

from je_auto_control.utils.action_journal import recorder
from je_auto_control.utils.action_journal.events import (
    SCHEMA_VERSION, STATUS_ERROR, ActionEvent, JournalFormatError,
)
from je_auto_control.utils.action_journal.sanitize import artifacts_of_step
from je_auto_control.utils.action_journal.store import read_events
from je_auto_control.utils.executor.action_executor import Executor


@pytest.fixture(autouse=True)
def _journal_off():
    recorder.stop_action_journal()
    yield
    recorder.stop_action_journal()


@pytest.fixture
def fake_executor():
    executor = Executor()

    def fake_save(file_path):
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write("pixels")
        return file_path

    def fake_read(file_path):
        with open(file_path, encoding="utf-8") as handle:
            return len(handle.read())

    def fake_trace():
        return {"trace_id": "0af7651916cd43dd8448eb211c80319c", "ok": True}

    def fake_report(name):
        from je_auto_control.utils.generate_report.report_path import write_report
        return write_report(name, "<html></html>")

    def fake_fail():
        raise RuntimeError("boom")

    executor.event_dict.update({
        "AC_fake_save": fake_save, "AC_fake_read": fake_read,
        "AC_fake_trace": fake_trace, "AC_fake_report": fake_report,
        "AC_fake_fail": fake_fail,
    })
    return executor


def _events(path, command):
    return [event for event in read_events(path) if event.command == command]


def test_a_file_the_step_wrote_is_an_artifact_and_one_it_read_is_not(tmp_path, fake_executor):
    journal = tmp_path / "journal.jsonl"
    shot = tmp_path / "shot.png"
    recorder.start_action_journal(journal, run_id="run-artifacts")
    fake_executor.execute_action([["AC_fake_save", {"file_path": str(shot)}]])
    # Make the input older than the step that reads it.
    import os
    old = shot.stat().st_mtime - 3600
    os.utime(shot, (old, old))
    fake_executor.execute_action([["AC_fake_read", {"file_path": str(shot)}]])
    recorder.stop_action_journal()
    saved = _events(journal, "AC_fake_save")[0]
    assert [dict(item) for item in saved.artifacts] == [
        {"kind": "image", "path": str(shot), "source": "file_path"}]
    assert _events(journal, "AC_fake_read")[0].artifacts == ()


def test_trace_id_in_the_result_and_a_written_report_are_recorded(tmp_path, fake_executor):
    journal = tmp_path / "journal.jsonl"
    report = tmp_path / "run.html"
    recorder.start_action_journal(journal)
    fake_executor.execute_action([
        ["AC_fake_trace"], ["AC_fake_report", {"name": str(report)}]])
    recorder.stop_action_journal()
    trace = _events(journal, "AC_fake_trace")[0].artifacts
    assert [dict(item) for item in trace] == [
        {"kind": "trace", "id": "0af7651916cd43dd8448eb211c80319c", "source": "trace_id"}]
    assert [dict(item) for item in _events(journal, "AC_fake_report")[0].artifacts] == [
        {"kind": "report", "path": str(report)}]


def test_an_artifact_noted_after_the_run_failed_lands_on_the_failed_step(
        tmp_path, fake_executor):
    journal = tmp_path / "journal.jsonl"
    recorder.start_action_journal(journal)
    fake_executor.execute_action([["AC_fake_fail"]])
    assert recorder.note_artifact("screenshot", path=str(tmp_path / "fail.png")) is True
    recorder.stop_action_journal()
    failed = _events(journal, "AC_fake_fail")[0]
    assert failed.status == STATUS_ERROR
    assert [dict(item) for item in failed.artifacts] == [
        {"kind": "screenshot", "path": str(tmp_path / "fail.png")}]


def test_error_snapshot_is_noted_on_the_journal(tmp_path, fake_executor, monkeypatch):
    from je_auto_control.utils.run_history import artifact_manager
    from je_auto_control.utils.run_history.history_store import HistoryStore
    import je_auto_control.wrapper.auto_control_screen as screen_module

    def fake_screenshot(file_path):
        with open(file_path, "wb") as handle:
            handle.write(b"png")

    monkeypatch.setattr(screen_module, "screenshot", fake_screenshot)
    store = HistoryStore()
    run = store.start_run("manual", "id", "script.json")
    journal = tmp_path / "journal.jsonl"
    recorder.start_action_journal(journal)
    fake_executor.execute_action([["AC_fake_fail"]])
    written = artifact_manager.capture_error_snapshot(run, tmp_path / "shots", store)
    recorder.stop_action_journal()
    assert written is not None
    assert [dict(item) for item in _events(journal, "AC_fake_fail")[0].artifacts] == [
        {"kind": "screenshot", "path": written}]


def test_note_artifact_does_nothing_without_a_journal():
    assert recorder.note_artifact("report", path="x.html") is False


def test_lines_without_the_field_read_as_before_and_steps_without_artifacts_omit_it(
        tmp_path, fake_executor):
    old = tmp_path / "old.jsonl"
    start = {"schema_version": 1, "record": "start", "run_id": "r", "step_id": "s-1",
             "sequence": 1, "command": "AC_x", "params": None, "status": "incomplete",
             "started_at": 1.0}
    end = {"schema_version": 1, "record": "end", "run_id": "r", "step_id": "s-1",
           "status": "ok", "finished_at": 2.0, "error": None, "outcome": None}
    old.write_text(json.dumps(start) + "\n" + json.dumps(end) + "\n", encoding="utf-8")
    events = read_events(old)
    assert events[0].artifacts == ()
    assert events[0].status == "ok"
    assert SCHEMA_VERSION == 1
    event = ActionEvent(run_id="r", step_id="s", sequence=1, command="AC_x")
    assert "artifacts" not in event.to_dict()
    assert "artifacts" not in event.end_dict()
    journal = tmp_path / "journal.jsonl"
    recorder.start_action_journal(journal)
    fake_executor.execute_action([["AC_fake_trace"], ["AC_fake_fail"]])
    recorder.stop_action_journal()
    lines = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert all("artifacts" not in line for line in lines if line["record"] == "start")
    assert sum("artifacts" in line for line in lines) == 1


def test_a_malformed_artifacts_value_is_refused(tmp_path):
    bad = tmp_path / "bad.jsonl"
    line = {"schema_version": 1, "record": "start", "run_id": "r", "step_id": "s-1",
            "sequence": 1, "command": "AC_x", "artifacts": [{"path": 3}]}
    bad.write_text(json.dumps(line) + "\n", encoding="utf-8")
    with pytest.raises(JournalFormatError):
        read_events(bad)


def test_unresolved_references_and_missing_files_are_not_artifacts(tmp_path):
    assert artifacts_of_step(
        {"file_path": "${out}", "path": str(tmp_path / "missing.png")}, None, 0.0) == []
