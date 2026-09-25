"""Script Builder: shown defaults, positional arguments, wrapped files, locales, flow bodies.

Selecting a hand-written step and editing any field wrote the form's shown
defaults back: ``detect_threshold`` 0.8 loosened an exact image match. Positional
arguments and extra entries were dropped on load, and a wrapped file lost its
other keys on save. French and German locales refused a decimal point; a
non-numeric RGB value broke the form; a new loop did not take children.
"""
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtGui import QValidator  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from je_auto_control.gui.script_builder.builder_tab import ScriptBuilderTab  # noqa: E402
from je_auto_control.gui.script_builder.step_form_view import StepFormView  # noqa: E402
from je_auto_control.gui.script_builder.step_list_view import StepTreeView  # noqa: E402
from je_auto_control.gui.script_builder.step_model import (  # noqa: E402
    Step, action_to_step, actions_to_steps, steps_to_actions,
)


@pytest.fixture(autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


# --- the model ------------------------------------------------------------------------------------------------

def test_positional_arguments_survive_a_round_trip():
    actions = [["AC_type_keyboard", ["a"]], ["AC_click_mouse", {"mouse_keycode": "mouse_left"}]]
    steps = actions_to_steps(actions)
    assert steps[0].args == ["a"] and steps_to_actions(steps) == actions


@pytest.mark.parametrize("action", [["AC_x", {}, "extra"], ["AC_x", "abc"]])
def test_shapes_the_builder_cannot_keep_are_refused(action):
    with pytest.raises(ValueError):
        action_to_step(action)


# --- the form ---------------------------------------------------------------------------------------------------

def _editor(form, name):
    editor = form._editors[name]
    return editor.property("line_edit") or editor


def test_editing_one_field_does_not_loosen_the_image_threshold():
    step = Step("AC_locate_and_click", {"image": "button.png", "mouse_keycode": "mouse_left"})
    form = StepFormView()
    form.load_step(step)
    _editor(form, "image").setText("other.png")
    assert step.params["image"] == "other.png"
    assert step.params.get("detect_threshold", 1.0) == 1.0


def test_a_decimal_point_is_accepted_under_a_comma_locale():
    previous = QLocale()
    QLocale.setDefault(QLocale("fr_FR"))
    try:
        form = StepFormView()
        form.load_step(Step("AC_locate_image_center", {"image": "a.png"}))
        validator = _editor(form, "detect_threshold").validator()
        assert validator.validate("0.8", 0)[0] == QValidator.State.Acceptable
    finally:
        QLocale.setDefault(previous)


def test_a_non_numeric_rgb_value_is_shown_as_written():
    form = StepFormView()
    form.load_step(Step("AC_wait_pixel", {"x": 1, "y": 2, "rgb": ["red", 0, 0]}))
    assert _editor(form, "rgb").text() == "['red', 0, 0]"


def test_a_positional_step_has_no_editors_to_overwrite_it():
    step = Step("AC_type_keyboard", args=["a"])
    form = StepFormView()
    form.load_step(step)
    assert form._editors == {} and step.params == {}


# --- the tree and the tab ----------------------------------------------------------------------------------------

def test_a_new_loop_takes_the_next_step_as_a_child():
    tree = StepTreeView()
    tree.add_step(Step("AC_loop", {"times": 2}))
    tree.setCurrentItem(tree.topLevelItem(0))
    tree.add_step(Step("AC_click_mouse", {"mouse_keycode": "mouse_left"}))
    [loop] = tree.root_steps()
    assert [child.command for child in loop.bodies["body"]] == ["AC_click_mouse"]


def test_a_wrapped_file_keeps_its_other_keys(monkeypatch, tmp_path):
    source, target = tmp_path / "in.json", tmp_path / "out.json"
    source.write_text(json.dumps({"meta": {"owner": "qa"}, "auto_control": [["AC_click_mouse"]]}),
                      encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    tab = ScriptBuilderTab()
    tab._on_load()
    tab._on_save()
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "meta": {"owner": "qa"}, "auto_control": [["AC_click_mouse"]]}
