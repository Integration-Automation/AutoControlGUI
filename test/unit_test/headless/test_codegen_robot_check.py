"""The structural check of generated Robot Framework source.

It is not the Robot parser (``robotframework`` is not installed here): these
tests pin what it accepts and the malformed shapes it reports.
"""
import pytest

from je_auto_control.utils.codegen import codegen
from je_auto_control.utils.codegen.codegen import generate_code
from je_auto_control.utils.codegen.robot_check import (
    RobotStructureError, check_robot_structure, require_robot_structure,
)

GOOD = """*** Settings ***
Documentation    A suite
Library    Collections

*** Variables ***
${NAME}    value
@{ITEMS}    a    b

*** Test Cases ***
First Flow
    [Documentation]    what it does
    ${actions}=    Evaluate    json.loads('[]')    json
    FOR    ${item}    IN    @{ITEMS}
        Log    ${item}
    END
    Log    done
    ...    continued

# a comment
Second Flow
\tLog    tab indented

*** Keywords ***
My Keyword
    [Arguments]    ${x}
    RETURN    ${x}
"""


def _problems(source):
    return check_robot_structure(source)


def test_a_well_formed_suite_has_no_problems():
    assert _problems(GOOD) == []
    require_robot_structure(GOOD)


@pytest.mark.parametrize("actions", [
    [["AC_click_mouse", {"mouse_keycode": "mouse_left", "x": 1, "y": 2}]],
    [["AC_write", {"write_string": "two  spaces ${HOME} ''' *** x ***"}],
     ["AC_loop", {"times": 2, "body": [["AC_set_var", {"name": "a", "value": 1}]]}]],
])
@pytest.mark.parametrize("name", ["recorded_flow", "*** Settings ***", "${x} | y", "#"])
def test_everything_the_renderer_emits_passes(actions, name):
    code = generate_code(actions, target="robot", name=name)
    assert _problems(code) == []


@pytest.mark.parametrize("source, expected", [
    ("Log    hello\n", "text before the first section header"),
    ("*** Settigns ***\n*** Test Cases ***\nT\n    Log    x\n", "unknown section header"),
    ("*** Settings ***\nDocumentation    x\n", "defines no test case"),
    ("*** Settings ***\n    Documentation    x\n*** Test Cases ***\nT\n    Log    x\n",
     "may not be indented"),
    ("*** Settings ***\nLibary    x\n*** Test Cases ***\nT\n    Log    x\n",
     "unknown setting 'Libary'"),
    ("*** Variables ***\nNAME    x\n*** Test Cases ***\nT\n    Log    x\n",
     "is not a variable name"),
    ("*** Test Cases ***\nEmpty\nOther\n    Log    x\n", "'Empty' has no body"),
    ("*** Test Cases ***\nSame\n    Log    x\nsame\n    Log    y\n", "defined twice"),
    ("*** Test Cases ***\n    Log    orphan\nT\n    Log    x\n", "no test case or keyword"),
    ("*** Test Cases ***\nT\n Log    one space\n    Log    x\n", "two or more spaces"),
    ("*** Test Cases ***\nT\n    ${x}=\n", "not followed by a keyword"),
    ("*** Test Cases ***\nT\n    [Nonsense]    x\n    Log    x\n", "unknown setting '[Nonsense]'"),
    ("*** Test Cases ***\nT\n    Log    ${unclosed\n", "opened and never closed"),
    ("*** Test Cases ***\nT\n    FOR    ${i}    IN    a\n        Log    ${i}\n",
     "not closed by END"),
    ("*** Test Cases ***\nT\n    Log    x\n    END\n", "END closes nothing"),
    ("*** Test Cases ***\nT\n    ...    x\n    Log    y\n", "nothing to continue"),
])
def test_malformed_shapes_are_reported_with_their_line(source, expected):
    problems = _problems(source)
    assert any(expected in problem for problem in problems), problems
    with pytest.raises(RobotStructureError):
        require_robot_structure(source)


def test_problems_name_the_line():
    problems = _problems("*** Test Cases ***\nT\n    Log    x\n    [Bad]    y\n")
    assert problems == ["line 4: unknown setting '[Bad]'"]


def test_a_renderer_defect_is_refused_instead_of_written(monkeypatch):
    monkeypatch.setitem(codegen._RENDERERS, "robot",
                        lambda *_args: "*** Test Cases ***\nBroken\n")
    with pytest.raises(RobotStructureError, match="has no body"):
        generate_code([["AC_set_var", {"name": "a", "value": 1}]], target="robot")


def test_the_candidate_manifest_says_which_check_ran(tmp_path):
    from je_auto_control.utils.action_journal import recorder
    from je_auto_control.utils.codegen.journal_import import generate_candidate_from_log
    from je_auto_control.utils.executor.action_executor import Executor
    recorder.stop_action_journal()
    journal = tmp_path / "journal.jsonl"
    recorder.start_action_journal(journal, run_id="robot-run")
    try:
        Executor().execute_action([["AC_set_var", {"name": "a", "value": 1}]])
    finally:
        recorder.stop_action_journal()
    robot = generate_candidate_from_log(journal, run_id="robot-run", target="robot")
    checks = robot.manifest["validation"]
    assert checks["ast"] is None
    assert checks["robot_structure"] is True
    assert checks["robot_parser"] is False
    python = generate_candidate_from_log(journal, run_id="robot-run", target="pytest")
    assert "robot_structure" not in python.manifest["validation"]
