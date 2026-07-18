"""Loading a step into the form must never lose the user's data.

Script Builder round-trips real files: builder_tab loads an action JSON, and on
save writes the steps back out. So anything the form drops on load is written
straight back over the user's file.
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")  # skips if Qt libs (e.g. libEGL) absent

from PySide6.QtWidgets import QApplication  # noqa: E402

from je_auto_control.gui.script_builder.step_form_view import (  # noqa: E402
    StepFormView,
)
from je_auto_control.gui.script_builder.step_model import (  # noqa: E402
    action_to_step, step_to_action,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _round_trip(action):
    """Load an action into the form exactly as selecting a step does."""
    step = action_to_step(action)
    view = StepFormView()
    view.load_step(step)
    return step_to_action(step)


@pytest.mark.parametrize("action", [
    # Params the schema has no field for — legitimate in hand-written JSON.
    ["AC_debug_trace", {"actions": [["AC_click_mouse",
                                     {"mouse_keycode": "mouse_left"}]],
                        "dry_run": True}],
    ["AC_skill_save", {"actions": [["AC_ok"]], "path": "s.json",
                       "name": "old"}],
    # A plain, fully-schema'd command must be untouched too.
    ["AC_execute_process", {"exe_path": "notepad.exe"}],
])
def test_loading_a_step_preserves_every_param(qapp, action):
    """Regression: two independent faults conspired to lose data.

    1. _commit_field rebuilt params from scratch out of spec.fields only, so
       any param without a schema field was dropped.
    2. Editors are wired to textChanged at build time while
       _populate_from_step fills them one at a time, so each setText committed
       a half-filled form — clobbering fields not yet populated (this is what
       turned AC_skill_save's "name" into None even though it *is* a field).

    Merely selecting the step was enough; builder_tab then saved the result.
    """
    assert _round_trip(action) == action


def test_editing_a_field_keeps_unknown_params(qapp):
    """A real edit must update its own field and leave the rest alone."""
    action = ["AC_debug_trace", {"actions": [["AC_ok"]], "dry_run": False}]
    step = action_to_step(action)
    view = StepFormView()
    view.load_step(step)

    editor = view._editors["dry_run"]
    editor.setChecked(True)          # a genuine user edit, post-population

    out = step_to_action(step)
    assert out[1]["dry_run"] is True
    assert out[1]["actions"] == [["AC_ok"]], "unknown param lost on edit"


def test_clearing_an_optional_field_drops_the_key(qapp):
    """The pre-existing semantic must survive: empty optional => no key."""
    action = ["AC_click_mouse", {"mouse_keycode": "mouse_left",
                                 "x": 10, "y": 20}]
    step = action_to_step(action)
    view = StepFormView()
    view.load_step(step)

    view._editors["x"].clear()       # user empties an optional field

    out = step_to_action(step)
    assert "x" not in out[1]
    assert out[1]["y"] == 20
