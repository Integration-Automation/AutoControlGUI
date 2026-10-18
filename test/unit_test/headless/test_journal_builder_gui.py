"""Offscreen journal forms retain nested bodies and expose read bounds."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication  # noqa: E402

from je_auto_control.gui.script_builder.step_form_view import StepFormView  # noqa: E402
from je_auto_control.gui.script_builder.step_model import action_to_step, step_to_action  # noqa: E402


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_capture_form_keeps_children_when_destination_changes(qapp, tmp_path):
    body = [["AC_set_var", {"name": "counter", "value": 1}]]
    action = ["AC_journal_capture", {"path": "before.jsonl", "run_id": "example", "body": body}]
    step = action_to_step(action)
    form = StepFormView()
    try:
        form.load_step(step)
        editor = form._editors["path"]
        (editor.property("line_edit") or editor).setText("after.jsonl")
        assert step_to_action(step) == ["AC_journal_capture", {
            "path": "after.jsonl", "run_id": "example", "body": body}]
        assert len(step.bodies["body"]) == 1
        form.resize(640, 280)
        form.show()
        qapp.processEvents()
        assert form.grab().save(str(tmp_path / "journal-capture-form.png"))
    finally:
        form.deleteLater()


def test_read_form_exposes_default_and_limit_bounds(qapp, tmp_path):
    step = action_to_step(["AC_journal_read", {"path": "events.jsonl", "run_id": "example"}])
    form = StepFormView()
    try:
        form.load_step(step)
        limit = form._editors["limit"]
        assert (limit.validator().bottom(), limit.validator().top(), limit.text()) == (1, 10000, "100")
        limit.setText("3")
        assert step_to_action(step) == ["AC_journal_read", {
            "path": "events.jsonl", "run_id": "example", "limit": 3}]
        form.resize(640, 240)
        form.show()
        qapp.processEvents()
        assert form.grab().save(str(tmp_path / "journal-read-form.png"))
    finally:
        form.deleteLater()
