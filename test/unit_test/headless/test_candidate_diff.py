"""What a journal candidate would change, as a diff (no Qt, temp files only)."""
import json

import pytest

import je_auto_control
from je_auto_control.utils.codegen.candidate_diff import (
    CandidateDiff, action_lines, diff_actions, diff_candidate, diff_candidate_against_file,
    diff_code,
)
from je_auto_control.utils.codegen.journal_import import (
    CandidateScript, JournalImportError, generate_candidate_from_log,
)
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.mcp_server.tools import _handlers_qa

_OLD = [["AC_set_var", {"name": "a", "value": 1}], ["AC_set_var", {"name": "b", "value": 2}]]
_NEW = [["AC_set_var", {"name": "a", "value": 1}], ["AC_set_var", {"name": "b", "value": 3}],
        ["AC_set_var", {"name": "c", "value": 4}]]


def _candidate(actions=None, code="print('new')\n"):
    return CandidateScript(code=code, manifest={"run_id": "r1"}, actions=list(actions or _NEW))


def test_an_action_diff_counts_what_was_added_and_removed():
    diff = diff_actions(_OLD, _NEW)
    assert isinstance(diff, CandidateDiff) and diff.kind == "actions"
    assert (diff.added, diff.removed, diff.identical) == (2, 1, False)
    rows = diff.text.splitlines()
    assert rows[0] == "--- current" and rows[1] == "+++ candidate"
    assert '-["AC_set_var", {"name": "b", "value": 2}]' in rows
    assert '+["AC_set_var", {"name": "b", "value": 3}]' in rows
    assert ' ["AC_set_var", {"name": "a", "value": 1}]' in rows       # context, unchanged


def test_identical_sides_have_an_empty_diff():
    diff = diff_actions(_OLD, json.loads(json.dumps(_OLD)))
    assert diff.identical and diff.text == "" and diff.to_dict()["identical"] is True


def test_key_order_is_not_a_change():
    assert diff_actions([["AC_x", {"a": 1, "b": 2}]], [["AC_x", {"b": 2, "a": 1}]]).identical


def test_a_change_deep_in_a_nested_body_shows_as_its_own_line():
    def loop(value):
        body = [["AC_set_var", {"name": f"variable_{index}", "value": index}] for index in range(6)]
        body[4][1]["value"] = value
        return [["AC_loop", {"times": 3, "body": body}]]

    assert len(action_lines(loop(1))) > 6, "a long nested action is spread over lines"
    diff = diff_actions(loop(1), loop(99))
    assert (diff.added, diff.removed) == (1, 1)
    assert any(row.startswith("+") and "99" in row for row in diff.text.splitlines()[2:])


def test_a_code_diff_is_line_by_line():
    diff = diff_code("a = 1\nb = 2\n", "a = 1\nb = 3\n", before_label="old.py")
    assert diff.kind == "code" and (diff.added, diff.removed) == (1, 1)
    assert diff.text.splitlines()[0] == "--- old.py" and "+b = 3" in diff.text


def test_diff_candidate_takes_exactly_one_side():
    candidate = _candidate()
    assert diff_candidate(candidate, actions=_OLD).kind == "actions"
    assert diff_candidate(candidate, code="print('old')\n").kind == "code"
    for arguments in ({}, {"actions": _OLD, "code": "x"}):
        with pytest.raises(JournalImportError) as raised:
            diff_candidate(candidate, **arguments)
        assert isinstance(raised.value, AutoControlException)
    with pytest.raises(JournalImportError):
        diff_candidate(candidate, actions=_OLD, context=-1)


def test_against_a_file_the_suffix_picks_what_is_compared(tmp_path):
    candidate = _candidate()
    actions_file = tmp_path / "flow.json"
    actions_file.write_text(json.dumps(_OLD), encoding="utf-8")
    by_actions = diff_candidate_against_file(candidate, actions_file)
    assert by_actions.kind == "actions" and by_actions.before_label == str(actions_file)
    script = tmp_path / "flow.py"
    script.write_text("print('old')\n", encoding="utf-8")
    by_code = diff_candidate_against_file(candidate, script)
    assert by_code.kind == "code" and (by_code.added, by_code.removed) == (1, 1)


def test_a_missing_file_makes_the_whole_candidate_new(tmp_path):
    candidate = _candidate(code="a = 1\nb = 2\n")
    assert diff_candidate_against_file(candidate, tmp_path / "none.py").added == 2
    assert diff_candidate_against_file(candidate, tmp_path / "none.json").added == len(_NEW)


def test_the_facade_exports_the_diff():
    for name in ("CandidateDiff", "diff_candidate", "diff_candidate_against_file"):
        assert name in je_auto_control.__all__ and hasattr(je_auto_control, name)


# --- the command and the MCP tool ---------------------------------------------------------------------------------

@pytest.fixture()
def journal(tmp_path):
    path = tmp_path / "run.jsonl"
    rows = [json.dumps({
        "schema_version": 1, "record": "start", "run_id": "run-1", "step_id": f"run-1-{index}",
        "sequence": index, "command": "AC_set_var", "status": "ok", "started_at": float(index),
        "finished_at": index + 0.5, "params": {"name": name, "value": index}})
        for index, name in enumerate(("a", "b"), start=1)]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_the_command_returns_a_diff_against_the_named_file(journal, tmp_path):
    candidate = generate_candidate_from_log(journal, run_id="run-1")
    previous = tmp_path / "previous.json"
    previous.write_text(json.dumps(candidate.actions[:1]), encoding="utf-8")
    command = executor.event_dict["AC_generate_code_from_journal"]
    result = command(str(journal), diff_against=str(previous))
    assert result["diff"]["kind"] == "actions" and result["diff"]["added"] == len(candidate.actions) - 1
    assert result["diff"]["removed"] == 0 and "diff" not in command(str(journal))


def test_the_diff_is_taken_before_the_output_overwrites_the_same_file(journal, tmp_path):
    output = tmp_path / "candidate.py"
    output.write_text("# an earlier export\n", encoding="utf-8")
    result = _handlers_qa.generate_code_from_log(str(journal), output=str(output),
                                                 diff_against=str(output))
    assert result["diff"]["kind"] == "code" and result["diff"]["removed"] == 1
    assert "-# an earlier export" in result["diff"]["text"]
    assert output.read_text(encoding="utf-8") == result["code"]
