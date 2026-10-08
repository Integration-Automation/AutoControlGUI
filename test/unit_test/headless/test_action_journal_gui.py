"""GUI affordances for the action journal: thin wrappers over the headless API.

Every dialog is replaced by a stub, so no window is shown and nothing is run.
"""
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QFileDialog, QInputDialog, QMessageBox,
)

from je_auto_control.gui import _journal_import  # noqa: E402
from je_auto_control.gui.recording_editor_tab import RecordingEditorTab  # noqa: E402
from je_auto_control.gui.run_history_tab import RunHistoryTab  # noqa: E402
from je_auto_control.gui.script_builder.builder_tab import ScriptBuilderTab  # noqa: E402
from je_auto_control.gui.script_builder.step_model import steps_to_actions  # noqa: E402
from je_auto_control.utils.action_journal import recorder  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _journal_off():
    recorder.stop_action_journal()
    yield
    recorder.stop_action_journal()


@pytest.fixture()
def dialogs(monkeypatch):
    """Stub every dialog; ``answers`` holds what each returns, ``shown`` what was said."""
    answers = {"open": "", "save": "", "run": None}
    shown = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *_a, **_k: (answers["open"], ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *_a, **_k: (answers["save"], ""))
    monkeypatch.setattr(
        QInputDialog, "getItem",
        lambda _parent, _title, _label, items, *_a, **_k: (
            answers["run"] or items[0], True))
    for name in ("information", "warning"):
        monkeypatch.setattr(QMessageBox, name,
                            lambda _parent, _title, text, *_a, _n=name: shown.append((_n, text)))
    answers["shown"] = shown
    return answers


def _journal(path, *runs):
    lines = []
    for run_id, commands in runs:
        for index, (command, extra) in enumerate(commands, start=1):
            lines.append(json.dumps({
                "schema_version": 1, "record": "start", "run_id": run_id,
                "step_id": f"{run_id}-{index}", "sequence": index, "command": command,
                "status": "ok", "started_at": float(index),
                "finished_at": index + 0.5, **extra}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_recording_editor_imports_a_journal_run_and_can_undo(qapp, tmp_path, dialogs):
    dialogs["open"] = _journal(
        tmp_path / "journal.jsonl",
        ("old", [("AC_write", {"params": {"write_string": "old"}})]),
        ("new", [("AC_write", {"params": {"write_string": "new"}}),
                 ("AC_get_mouse_position", {})]))
    tab = RecordingEditorTab()
    tab._actions = [["AC_a"]]
    assert "re_import_journal" in [key for key, _handler in tab.menu_actions()]
    tab._import_journal()  # the newest run is offered first
    assert tab._actions == [["AC_write", {"write_string": "new"}], ["AC_get_mouse_position"]]
    assert "journal run new" in tab._status.text()
    assert '"new"' in tab._preview.toPlainText()
    tab._undo()
    assert tab._actions == [["AC_a"]]
    tab.deleteLater()


def test_observed_path_is_announced_before_the_candidate_opens(qapp, tmp_path, dialogs):
    dialogs["open"] = _journal(
        tmp_path / "journal.jsonl",
        ("run", [("AC_write", {"parent_id": "gone", "params": {"write_string": "x"}})]))
    tab = ScriptBuilderTab()
    tab._on_import_journal()
    assert steps_to_actions(tab._tree.root_steps()) == [["AC_write", {"write_string": "x"}]]
    kind, text = dialogs["shown"][0]
    assert kind == "information"
    assert _journal_import._t("jr_observed_only") in text
    assert "Imported journal run run: 1 step(s)" in tab._result.toPlainText()
    tab.deleteLater()


def test_cancel_and_bad_files_leave_the_tab_alone(qapp, tmp_path, dialogs):
    tab = RecordingEditorTab()
    tab._actions = [["AC_a"]]
    tab._import_journal()  # the file dialog was cancelled
    assert tab._actions == [["AC_a"]] and dialogs["shown"] == []
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"schema_version": 7, "run_id": "r", "step_id": "s"}\n', encoding="utf-8")
    dialogs["open"] = str(bad)
    tab._import_journal()
    assert tab._actions == [["AC_a"]]
    assert dialogs["shown"][0][0] == "warning" and "schema_version" in dialogs["shown"][0][1]
    tab.deleteLater()


def test_run_history_tab_starts_stops_and_exports(qapp, tmp_path, dialogs):
    tab = RunHistoryTab()
    tab._timer.stop()
    keys = [key for key, _handler in tab.menu_actions()]
    assert {"rh_journal_start", "rh_journal_stop", "rh_journal_candidate"} <= set(keys)
    assert tab._journal_label.text() == _journal_import._t("rh_journal_off")

    journal = tmp_path / "live.jsonl"
    dialogs["save"] = str(journal)
    tab._start_journal()
    status = recorder.action_journal_status()
    assert status["active"] is True and status["path"] == str(journal.resolve())
    assert status["run_id"] in tab._journal_label.text()
    tab._start_journal()  # a second start is refused, and said so
    assert dialogs["shown"][-1][0] == "warning"
    tab._stop_journal()
    assert recorder.action_journal_status()["active"] is False
    assert tab._journal_label.text() == _journal_import._t("rh_journal_off")

    dialogs["open"] = _journal(
        tmp_path / "journal.jsonl",
        ("run", [("AC_write", {"params": {"write_string": "x"}})]))
    output = tmp_path / "test_candidate.py"
    dialogs["save"] = str(output)
    tab._export_journal_candidate()
    assert "def test_journal_run_run" in output.read_text(encoding="utf-8")
    manifest = json.loads((tmp_path / "test_candidate.py.manifest.json").read_text(
        encoding="utf-8"))
    assert manifest["run_id"] == "run" and manifest["executed"] is False
    tab.deleteLater()


def test_strings_exist_in_every_language():
    from je_auto_control.gui.language_wrapper import (
        english, japanese, simplified_chinese, traditional_chinese,
    )
    keys = ("rh_journal_start", "rh_journal_stop", "rh_journal_candidate",
            "rh_journal_off", "rh_journal_on", "re_import_journal", "sb_import_journal",
            "jr_dialog_open", "jr_dialog_start", "jr_dialog_save_code", "jr_pick_run",
            "jr_no_runs", "jr_observed_only")
    for module in (english, japanese, simplified_chinese, traditional_chinese):
        catalogue = next(value for value in vars(module).values()
                         if isinstance(value, dict) and "rh_no_artifact" in value)
        assert all(catalogue.get(key) for key in keys), module.__name__
