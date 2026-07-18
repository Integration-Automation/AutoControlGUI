"""Round-3 GUI audit regressions for the Script Builder model, tree and form.

Covers:
* drag-drop no longer silently desyncs the Step model (finding 1);
* ``Step`` uses identity equality so duplicate steps are edited correctly
  (finding 2);
* ``actions_to_steps`` unwraps the ``auto_control`` mapping and rejects
  shapes it cannot represent instead of fabricating garbage (finding 3);
* ``_commit_field`` survives an unparseable value in one field instead of
  aborting/freezing every later edit (finding 4).
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QAbstractItemView, QApplication  # noqa: E402

from je_auto_control.gui.script_builder.command_schema import (  # noqa: E402
    COMMAND_SPECS,
)
from je_auto_control.gui.script_builder.step_form_view import (  # noqa: E402
    StepFormView,
)
from je_auto_control.gui.script_builder.step_list_view import (  # noqa: E402
    StepTreeView,
)
from je_auto_control.gui.script_builder.step_model import (  # noqa: E402
    Step, action_to_step, actions_to_steps, steps_to_actions,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _command_with_body_key():
    for command, spec in COMMAND_SPECS.items():
        if spec.body_keys:
            return command, spec.body_keys[0]
    return None, None


# --- Finding 2: identity equality ------------------------------------------

def test_step_uses_identity_equality():
    a = Step(command="AC_ok")
    b = Step(command="AC_ok")  # structurally identical, distinct object
    assert a == a
    assert a != b
    steps = [a, b]
    steps.remove(b)
    assert steps == [a]  # removed the selected object, not the first equal one


def test_duplicate_root_delete_targets_selected(qapp):
    tree = StepTreeView()
    first = Step(command="AC_ok")
    second = Step(command="AC_ok")  # duplicate
    tree.load_steps([first, second])
    tree.setCurrentItem(tree.topLevelItem(1))  # select the second (duplicate)
    tree.remove_selected()
    remaining = tree.root_steps()
    assert len(remaining) == 1
    assert remaining[0] is first  # the first survived, not a value match


# --- Finding 1: drag-drop disabled + nested delete stays in sync -----------

def test_item_drag_drop_is_disabled(qapp):
    tree = StepTreeView()
    # InternalMove reorders items without touching the model; it must be off.
    assert tree.dragDropMode() == QAbstractItemView.DragDropMode.NoDragDrop


def test_nested_duplicate_delete_syncs_model(qapp):
    command, body_key = _command_with_body_key()
    if command is None:
        pytest.skip("no flow-control command with body_keys in the schema")
    child_a = Step(command="AC_ok")
    child_b = Step(command="AC_ok")  # duplicate of child_a
    parent = Step(command=command, bodies={body_key: [child_a, child_b]})
    tree = StepTreeView()
    tree.load_steps([parent])
    parent_item = tree.topLevelItem(0)
    body_item = parent_item.child(0)
    tree.setCurrentItem(body_item.child(1))  # the duplicate nested child
    tree.remove_selected()  # must not raise AttributeError
    assert parent.bodies[body_key] == [child_a]
    assert parent.bodies[body_key][0] is child_a


# --- Finding 3: actions_to_steps input shapes ------------------------------

def test_actions_to_steps_unwraps_auto_control_mapping():
    steps = actions_to_steps({"auto_control": [["AC_ok"]]})
    # Before the fix a dict was iterated as keys, so "auto_control" became a
    # fabricated command "a".
    assert [s.command for s in steps] == ["AC_ok"]


def test_actions_to_steps_round_trips_plain_list():
    steps = actions_to_steps([["AC_ok"]])
    assert steps_to_actions(steps) == [["AC_ok"]]


def test_actions_to_steps_rejects_dict_entry():
    with pytest.raises(ValueError):
        actions_to_steps([{"foo": "bar"}])


def test_actions_to_steps_rejects_string_action():
    with pytest.raises(ValueError):
        action_to_step("auto_control")  # used to become command "a"


def test_actions_to_steps_rejects_non_list():
    with pytest.raises(ValueError):
        actions_to_steps(42)


def test_actions_to_steps_rejects_mapping_without_key():
    with pytest.raises(ValueError):
        actions_to_steps({"not_auto_control": []})


# --- Finding 4: commit survives an unparseable field -----------------------

def test_commit_survives_unparseable_int_field(qapp):
    # AC_human_type has a STRING field (text) and an optional INT field (seed).
    step = action_to_step(["AC_human_type", {"text": "hi", "seed": 5}])
    view = StepFormView()
    view.load_step(step)
    # A loaded float in an int field (setText bypasses the validator), exactly
    # like a JSON "100.0" landing in an int editor.
    view._editors["seed"].setText("100.0")
    # Editing another field fires _commit_field; it must not abort on the bad
    # int, so the string edit is persisted.
    view._editors["text"].setText("changed")
    assert step.params["text"] == "changed"
