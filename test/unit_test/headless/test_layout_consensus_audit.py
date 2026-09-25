"""Element geometry, grounding consensus, column layout, recording edits, flow debugging, compliance.

Readers that knew one element shape dropped the others: set-of-marks skipped
OCR boxes and consensus put accessibility elements at (0, 0). Infinite points
escaped as OverflowError; columns left of x = 0 vanished; a ${var} sleep broke
the editors; a wrapped action file broke the debugger; a framework name as a
string was walked letter by letter.
"""
import types

import pytest

from je_auto_control.utils.accessibility.element import AccessibilityElement, element_box


@pytest.mark.parametrize("element, box", [
    ({"bbox": [1, 2, 3, 4]}, (1, 2, 3, 4)),
    ({"bounds": (1, 2, 3, 4)}, (1, 2, 3, 4)),
    ({"x": 1, "y": 2, "width": 3, "height": 4}, (1, 2, 3, 4)),
    (AccessibilityElement("OK", "button", (1, 2, 3, 4)), (1, 2, 3, 4)),
    (types.SimpleNamespace(x=1, y=2, width=3, height=4), (1, 2, 3, 4)),
    ({"text": "no geometry"}, None),
    ({"bbox": [1, 2]}, None),
])
def test_element_box_reads_every_shape(element, box):
    assert element_box(element) == box


def test_ocr_boxes_are_marked():
    from je_auto_control.utils.set_of_marks.set_of_marks import mark_elements
    marks = mark_elements([{"x": 10, "y": 10, "width": 80, "height": 20, "text": "OK"}])
    assert [(mark["id"], mark["center"]) for mark in marks] == [(1, [50, 20])]


def test_consensus_votes_by_real_geometry_and_refuses_infinite_points():
    from je_auto_control.utils.grounding_consensus.grounding_consensus import (
        consensus_element, consensus_point,
    )
    far = {"name": "far", "bounds": (0, 0, 20, 20)}
    near = {"name": "near", "bounds": (480, 480, 40, 40)}
    winner, agreement = consensus_element([[500, 500], [501, 499]], [far, near])
    assert (winner["name"], agreement) == ("near", 1.0)
    assert consensus_element([[500, 500]], [{"name": "no geometry"}]) is None
    with pytest.raises(ValueError, match="finite"):
        consensus_point([[float("inf"), 5]])


def _word(x, y, text, width=40):
    return {"x": x, "y": y, "width": width, "height": 20, "text": text}


def test_columns_left_of_the_primary_screen_are_found():
    from je_auto_control.utils.column_layout.column_layout import column_gutters, detect_borderless_table
    boxes = [_word(-1910, 0, "Name"), _word(-1790, 0, "Age"), _word(-1910, 30, "Ann"), _word(-1790, 30, "30")]
    assert column_gutters(boxes)[0]["start"] < 0
    assert detect_borderless_table(boxes)["rows"] == [["Name", "Age"], ["Ann", "30"]]
    straddling = [_word(-70, 0, "Name", 50), _word(50, 0, "Age"), _word(-70, 30, "Ann", 50), _word(50, 30, "30")]
    assert detect_borderless_table(straddling)["rows"] == [["Name", "Age"], ["Ann", "30"]]


def test_a_variable_sleep_is_left_alone_by_the_editors():
    from je_auto_control.utils.recording_edit.editor import adjust_delays, merge_sleeps
    actions = [["AC_sleep", {"seconds": "${wait}"}], ["AC_sleep", {"seconds": 1}], ["AC_sleep", {"seconds": 2}]]
    assert adjust_delays(actions, 2.0)[0] == ["AC_sleep", {"seconds": "${wait}"}]
    assert merge_sleeps(actions) == [["AC_sleep", {"seconds": "${wait}"}], ["AC_sleep", {"seconds": 3.0}]]


def test_the_debugger_takes_a_wrapped_action_file():
    from je_auto_control.utils.flow_debugger.flow_debugger import FlowDebugger, trace_actions
    program = {"auto_control": [["AC_set_var", {"name": "a", "value": 5}]]}
    assert [step["command"] for step in trace_actions(program)] == ["AC_set_var"]
    assert FlowDebugger(program).step()["command"] == "AC_set_var"


def test_one_framework_by_name_and_evidence_that_is_not_a_mapping():
    from je_auto_control.utils.compliance.compliance_report import build_compliance_report
    report = build_compliance_report({}, frameworks="SOC2")
    assert {control["framework"] for control in report["controls"]} == {"SOC2"}
    with pytest.raises(ValueError, match="mapping"):
        build_compliance_report("mfa_enabled")


def test_the_overflow_check_reads_ocr_boxes():
    from je_auto_control.utils.i18n_test.i18n_test import check_overflow
    assert check_overflow([{"x": 0, "y": 0, "width": 20, "height": 20, "text": "Einstellungen speichern"}])
