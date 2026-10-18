"""Manual GUI controls preserve opt-out behavior and link explicit captures."""
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit

import je_auto_control as ac
from je_auto_control.gui.manual_run_controls import ManualRunControls
from je_auto_control.gui._script_tab import ScriptTabMixin
from je_auto_control.gui.script_builder.builder_tab import ScriptBuilderTab
from je_auto_control.gui.script_builder.step_model import action_to_step
from je_auto_control.utils.run_history import manual as manual_module


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path, monkeypatch):
    value = ac.HistoryStore(tmp_path / "history.sqlite")
    monkeypatch.setattr(manual_module, "default_history_store", value)
    yield value
    value.close()


def test_controls_default_to_no_recording_or_database(app, store):
    controls = ManualRunControls()
    try:
        assert not controls.record_history.isChecked() and controls.journal_path.text() == ""
        with controls.capture(source_id="test", script_path="<test>"):
            pass
        assert store._conn is None
    finally:
        controls.deleteLater()


@pytest.mark.parametrize("enabled", [False, True])
def test_editor_capture_preserves_result_and_links_opted_in_owner(app, store, tmp_path, enabled):
    controls = ManualRunControls()
    journal = tmp_path / "editor.jsonl"
    controls.record_history.setChecked(enabled)
    controls.journal_path.setText(str(journal))
    editor, output = QTextEdit(), QTextEdit()
    editor.setPlainText(json.dumps([["AC_set_var", {"name": "x", "value": 1}]]))
    host = SimpleNamespace(script_editor=editor, script_result_text=output, script_history_controls=controls)
    try:
        ScriptTabMixin._execute_manual_script(host)
        assert json.loads(output.toPlainText()) and len(ac.read_events(journal)) == 2
        rows = store.list_runs()
        assert len(rows) == int(enabled)
        if enabled:
            assert rows[0].status == "ok" and len(store.journals_for_run(rows[0].id)) == 1
    finally:
        controls.deleteLater()
        editor.deleteLater()
        output.deleteLater()


def test_file_execution_records_its_source_path(app, store, tmp_path):
    controls = ManualRunControls()
    controls.record_history.setChecked(True)
    script = tmp_path / "script.json"
    script.write_text('[["AC_set_var", {"name": "x", "value": 1}]]', encoding="utf-8")
    source, output = QLineEdit(str(script)), QTextEdit()
    host = SimpleNamespace(script_path_input=source, script_result_text=output, script_history_controls=controls)
    try:
        ScriptTabMixin._execute_script(host)
        assert store.list_runs()[0].script_path == str(script)
        assert json.loads(output.toPlainText())
    finally:
        for widget in (controls, source, output):
            widget.deleteLater()


def test_builder_records_with_optional_journal_without_result_wrapper(app, store, tmp_path):
    builder = ScriptBuilderTab()
    path = tmp_path / "builder.jsonl"
    try:
        builder._capture.record_history.setChecked(True)
        builder._capture.journal_path.setText(str(path))
        builder._tree.add_step(action_to_step(["AC_set_var", {"name": "x", "value": 1}]))
        builder._on_run()
        result = json.loads(builder._result.toPlainText())
        assert result and "history_id" not in result
        row = store.list_runs()[0]
        assert row.status == "ok" and len(store.journals_for_run(row.id)) == 1
    finally:
        builder.deleteLater()


def test_capture_command_form_keeps_body_when_metadata_changes(app):
    from je_auto_control.gui.script_builder.step_form_view import StepFormView
    from je_auto_control.gui.script_builder.step_model import step_to_action
    body = [["AC_get_var", {"name": "x"}]]
    step = action_to_step(["AC_history_capture", {"source_id": "before", "body": body}])
    form = StepFormView()
    try:
        form.load_step(step)
        form._editors["source_id"].setText("after")
        result = step_to_action(step)
        assert result[1]["source_id"] == "after" and result[1]["body"] == body
    finally:
        form.deleteLater()


def test_directory_execution_records_one_batch_and_all_snapshots(app, store, tmp_path):
    directory = tmp_path / "scripts"
    directory.mkdir()
    for index in range(2):
        (directory / f"{index}.json").write_text(
            json.dumps([["AC_set_var", {"name": f"x{index}", "value": index}]]), encoding="utf-8")
    controls = ManualRunControls()
    controls.record_history.setChecked(True)
    journal = tmp_path / "directory.jsonl"
    controls.journal_path.setText(str(journal))
    source, output = QLineEdit(str(directory)), QTextEdit()
    host = SimpleNamespace(script_dir_input=source, script_result_text=output, script_history_controls=controls)
    try:
        ScriptTabMixin._execute_dir(host)
        assert len(json.loads(output.toPlainText())) == 2
        assert len(store.list_runs()) == 1 and len(ac.read_events(journal)) == 4
        assert store.list_runs()[0].script_path == str(directory)
    finally:
        for widget in (controls, source, output):
            widget.deleteLater()


def test_manual_controls_retranslate_without_resetting_options(app):
    from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
    controls = ManualRunControls()
    old = language_wrapper.language
    try:
        controls.record_history.setChecked(True)
        controls.journal_path.setText("events.jsonl")
        language_wrapper.reset_language("Japanese")
        controls.retranslate()
        assert controls.record_history.text() == "実行履歴に記録"
        assert controls.record_history.isChecked() and controls.journal_path.text() == "events.jsonl"
    finally:
        language_wrapper.reset_language(old)
        controls.deleteLater()
