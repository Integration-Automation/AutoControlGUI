"""The Flow Editor reads and writes action files as the Script Builder does.

It opened files with plain UTF-8 (a Notepad file with a BOM failed), wrote them
with a non-atomic open(), and saved a wrapped file as a bare list.
"""
import json
import os

import pytest

from je_auto_control.gui.script_builder.step_model import load_action_file, save_action_file

_WRAPPED = {"meta": {"owner": "qa"}, "auto_control": [["AC_click_mouse", {"mouse_keycode": "mouse_left"}]]}


def test_a_wrapped_file_round_trips_with_its_other_keys(tmp_path):
    source, target = tmp_path / "in.json", tmp_path / "out.json"
    source.write_text(json.dumps(_WRAPPED), encoding="utf-8")
    steps, extras = load_action_file(str(source))
    save_action_file(str(target), steps, extras)
    assert json.loads(target.read_text(encoding="utf-8")) == _WRAPPED


def test_a_bare_list_stays_a_bare_list(tmp_path):
    source = tmp_path / "in.json"
    source.write_text(json.dumps(_WRAPPED["auto_control"]), encoding="utf-8")
    steps, extras = load_action_file(str(source))
    save_action_file(str(source), steps, extras)
    assert extras is None and json.loads(source.read_text(encoding="utf-8")) == _WRAPPED["auto_control"]


def test_the_flow_editor_opens_a_file_with_a_bom_and_saves_its_keys(monkeypatch, tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from je_auto_control.gui.flow_editor.tab import FlowEditorTab
    app = QApplication.instance() or QApplication([])
    source, target = tmp_path / "in.json", tmp_path / "out.json"
    source.write_text(chr(0xFEFF) + json.dumps(_WRAPPED), encoding="utf-8")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    tab = FlowEditorTab()
    tab._on_open()
    tab._on_save()
    assert warnings == []
    assert json.loads(target.read_text(encoding="utf-8")) == _WRAPPED
    tab.deleteLater()
    app.processEvents()
