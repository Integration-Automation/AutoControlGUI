"""Candidate scripts built from an action journal.

Journals are produced by a private executor running fake commands, or written
by hand as JSON lines; generation itself must never reach a device.
"""
import ast
import json

import pytest

import je_auto_control as ac
from je_auto_control import cli
from je_auto_control.utils.action_journal import recorder
from je_auto_control.utils.action_journal.events import JournalFormatError
from je_auto_control.utils.codegen.journal_import import (
    CandidateScript, JournalImportError, generate_candidate_from_log,
)
from je_auto_control.utils.executor.action_executor import Executor

PASSWORD = "hunter2-Zq9!x"


@pytest.fixture(autouse=True)
def _journal_off():
    recorder.stop_action_journal()
    yield
    recorder.stop_action_journal()


def _record(path, run_id, actions, extra=None):
    """Journal ``actions`` on a private executor whose device commands are fakes."""
    executor = Executor()
    executor.event_dict.update({
        "AC_click_mouse": lambda **_kwargs: None,
        "AC_write": lambda **_kwargs: None,
        **(extra or {}),
    })
    recorder.start_action_journal(path, run_id=run_id)
    try:
        executor.execute_action(actions)
    finally:
        recorder.stop_action_journal()


def _line(step, sequence, command, **fields):
    return json.dumps({
        "schema_version": 1, "record": "start", "run_id": "hand",
        "step_id": step, "sequence": sequence, "command": command,
        "status": "ok", "started_at": float(sequence),
        "finished_at": sequence + 0.5, **fields})


def _write(path, *lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture()
def device_calls(monkeypatch):
    """Every action the executor would really dispatch while a test runs."""
    calls = []
    monkeypatch.setattr(
        Executor, "_execute_event", lambda _self, action: calls.append(action))
    return calls


def test_run_filter_and_provenance(tmp_path):
    path = tmp_path / "journal.jsonl"
    script = [
        ["AC_click_mouse", {"mouse_keycode": "mouse_left", "x": 10, "y": 20}],
        ["AC_loop", {"times": 2, "body": [["AC_write", {"write_string": "hi"}]]}],
    ]
    _record(path, "other-run", [["AC_write", {"write_string": "noise"}]])
    selected_run = "run-42"
    _record(path, selected_run, script)

    candidate = generate_candidate_from_log(path, run_id=selected_run)
    assert isinstance(candidate, CandidateScript)
    assert candidate.manifest['run_id'] == selected_run
    assert candidate.actions == script  # the loop is rebuilt, not unrolled
    assert candidate.observed_path_only is False
    assert "noise" not in candidate.code
    steps = candidate.manifest["steps"]
    assert [step["command"] for step in steps] == ["AC_click_mouse", "AC_loop"]
    assert all(step["mode"] == "recorded" and step["emitted"] for step in steps)
    lines = path.read_text(encoding="utf-8").splitlines()
    for step in steps:  # each step points at the line it was read from
        source = json.loads(lines[step["line"] - 1])
        assert source["command"] == step["command"] and source["run_id"] == selected_run
    assert candidate.manifest["event_count"] == 4
    assert candidate.manifest["validation"] == {
        "ast": True, "unknown_commands": [], "dry_run": True}
    assert candidate.manifest["executed"] is False
    ast.parse(candidate.code)
    assert "raise_on_error=True" in candidate.code


def test_observed_branch_is_labelled(tmp_path):
    # The journal starts inside a block (the if's own line is missing), and a
    # macro is called that this run never defined.
    path = _write(
        tmp_path / "journal.jsonl",
        _line("t-2", 2, "AC_click_mouse", parent_id="t-1", params={"x": 1, "y": 2}),
        _line("t-3", 3, "AC_call_macro", params={"name": "login"}),
        _line("t-4", 4, "AC_write", parent_id="t-3", params={"write_string": "ada"}),
    )
    candidate = generate_candidate_from_log(path, run_id="hand")
    assert candidate.observed_path_only is True
    assert candidate.manifest["observed_path_only"] is True
    assert candidate.actions == [
        ["AC_click_mouse", {"x": 1, "y": 2}], ["AC_write", {"write_string": "ada"}]]
    modes = {step["step_id"]: (step["mode"], step["emitted"])
             for step in candidate.manifest["steps"]}
    assert modes == {"t-2": ("observed", True), "t-3": ("observed", False),
                     "t-4": ("observed", True)}
    text = " ".join(candidate.warnings)
    assert "observed" in text and "'login' is not defined" in text
    # Nothing that did not run is invented: no branch, no macro call.
    assert "AC_call_macro" not in candidate.code and "AC_if" not in candidate.code


def test_a_macro_defined_in_the_run_is_rebuilt_not_observed(tmp_path):
    path = tmp_path / "journal.jsonl"
    script = [
        ["AC_define_macro", {"name": "greet", "body": [
            ["AC_write", {"write_string": "hi"}]]}],
        ["AC_call_macro", {"name": "greet"}],
    ]
    _record(path, "macro", script)
    candidate = generate_candidate_from_log(path, run_id="macro")
    assert candidate.actions == script and candidate.observed_path_only is False


def test_secret_reference_survives_codegen(tmp_path):
    path = tmp_path / "journal.jsonl"
    _record(path, "secrets", [
        ["AC_fake_login", {"user": "ada", "password": "${secrets.db_password}"}],
        ["AC_fake_login", {"user": "bob", "password": PASSWORD}],
    ], extra={"AC_fake_login": lambda **_kwargs: None})
    candidate = generate_candidate_from_log(path, run_id="secrets", target="python")
    assert "${secrets.db_password}" in candidate.code
    assert candidate.actions[0][1]["password"] == "${secrets.db_password}"
    # The literal was masked before it reached the file, so the candidate
    # cannot hold it -- and it does not replay the mask as if it were a value.
    assert PASSWORD not in candidate.code and PASSWORD not in json.dumps(candidate.manifest)
    assert candidate.actions[1][1]["password"] == "${journal_redacted_1_1}"
    assert "'***'" not in candidate.code
    assert any("params.password is not replayable" in text for text in candidate.warnings)
    # AC_fake_login is unknown outside this test: reported, and the dry run skipped.
    validation = candidate.manifest["validation"]
    assert validation["unknown_commands"] == ["AC_fake_login"]
    assert validation["dry_run"] is False
    assert any("unknown command(s)" in text for text in candidate.warnings)


def test_generation_has_no_device_effect(tmp_path, device_calls, monkeypatch):
    path = tmp_path / "journal.jsonl"
    _write(
        path,
        _line("t-1", 1, "AC_click_mouse", params={"mouse_keycode": "mouse_left"}),
        _line("t-2", 2, "AC_write",
              params={"write_string": "__import__('os').system('calc')"}),
        _line("t-3", 3, "AC_shell_command", params={"command": "calc"}),
    )
    monkeypatch.setattr("builtins.eval", lambda *_args, **_kwargs: device_calls.append("eval"))
    monkeypatch.setattr("builtins.exec", lambda *_args, **_kwargs: device_calls.append("exec"))
    for target in ("pytest", "python", "robot"):
        for style in ("actions", "calls"):
            candidate = generate_candidate_from_log(
                path, run_id="hand", target=target, style=style)
            assert candidate.manifest["validation"]["dry_run"] is True
    assert device_calls == []
    assert recorder.action_journal_status()["active"] is False


def test_retry_attempts_are_counted_and_only_the_last_is_observed(tmp_path):
    path = tmp_path / "journal.jsonl"
    state = {"left": 2}

    def flaky(**_kwargs):
        state["left"] -= 1
        if state["left"] >= 0:
            raise RuntimeError("not yet")

    retry = ["AC_retry", {"max_attempts": 5, "backoff": 0, "body": [
        ["AC_write", {"write_string": "a"}], ["AC_fake_flaky", {}]]}]
    _record(path, "retry", [retry], extra={"AC_fake_flaky": flaky})
    candidate = generate_candidate_from_log(path, run_id="retry")
    assert candidate.actions == [retry]
    assert candidate.manifest["steps"][0]["attempts"] == 3

    # The same run with the block's arguments lost: only the final attempt.
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for line in lines:
        if line.get("command") == "AC_retry":
            line["unreplayable"] = {"params.body": "not JSON-serialisable (generator)"}
    _write(path, *(json.dumps(line) for line in lines))
    observed = generate_candidate_from_log(path, run_id="retry")
    assert observed.observed_path_only is True
    assert observed.actions == [["AC_write", {"write_string": "a"}], ["AC_fake_flaky", {}]]
    assert observed.manifest["steps"][0]["attempts"] == 3


def test_parallel_block_is_emitted_once_with_its_branches(tmp_path):
    path = tmp_path / "journal.jsonl"
    # A branch runs on a fresh executor that keeps its own stock commands, so
    # only a command with a name of its own stays a fake inside one.
    script = [["AC_parallel", {"branches": [
        [["AC_fake_type", {"text": "a"}]], [["AC_fake_type", {"text": "b"}]]]}]]
    _record(path, "par", script, extra={"AC_fake_type": lambda **_kwargs: None})
    candidate = generate_candidate_from_log(path, run_id="par")
    assert candidate.actions == script
    assert candidate.manifest["event_count"] == 3
    assert [step["command"] for step in candidate.manifest["steps"]] == ["AC_parallel"]


def test_steps_run_by_a_thread_pool_inside_a_block_are_not_emitted_twice(tmp_path):
    path = _write(
        tmp_path / "journal.jsonl",
        _line("t-1", 1, "AC_run_dag", thread=1, finished_at=9.0,
              params={"definition": {"nodes": []}}),
        _line("t-2", 2, "AC_write", thread=2, params={"write_string": "inside"}),
        _line("t-3", 10, "AC_write", thread=2, params={"write_string": "after"}),
    )
    candidate = generate_candidate_from_log(path, run_id="hand")
    assert [action[0] for action in candidate.actions] == ["AC_run_dag", "AC_write"]
    assert candidate.actions[1][1] == {"write_string": "after"}
    detached = [step for step in candidate.manifest["steps"] if step["mode"] == "detached"]
    assert [step["step_id"] for step in detached] == ["t-2"]


def test_failed_and_unfinished_steps_are_flagged_not_dropped(tmp_path):
    path = _write(
        tmp_path / "journal.jsonl",
        _line("t-1", 1, "AC_write", status="error", error="RuntimeError('x')",
              params={"write_string": "a"}),
        _line("t-2", 2, "AC_write", status="incomplete", finished_at=None,
              params={"write_string": "b"}),
        "{torn",
    )
    candidate = generate_candidate_from_log(path, run_id="hand")
    assert len(candidate.actions) == 2
    text = " ".join(candidate.warnings)
    assert "1 emitted step(s) failed" in text and "did not finish" in text
    assert "skipped unreadable line(s) 3" in text


def test_bad_input_is_refused(tmp_path):
    path = _write(tmp_path / "journal.jsonl", _line("t-1", 1, "AC_write", params={}))
    with pytest.raises(JournalImportError):
        generate_candidate_from_log(path, run_id="absent")
    with pytest.raises(JournalImportError):
        generate_candidate_from_log(path, run_id="hand", target="bash")
    with pytest.raises(JournalImportError):
        generate_candidate_from_log(path, run_id="hand", style="eval")
    _write(path, json.dumps({"schema_version": 99, "run_id": "hand", "step_id": "t"}))
    with pytest.raises(JournalFormatError):
        generate_candidate_from_log(path, run_id="hand")
    assert issubclass(JournalImportError, ac.AutoControlException)
    assert ac.generate_candidate_from_log is generate_candidate_from_log


def test_cli_from_log(tmp_path, capsys, device_calls):
    path = tmp_path / "journal.jsonl"
    _write(path, _line("t-1", 1, "AC_write", params={"write_string": "hello"}))
    assert cli.main(["codegen", "--from-log", str(path)]) == 0
    out = capsys.readouterr().out
    assert "def test_journal_run_hand" in out and "'hello'" in out

    output, manifest = tmp_path / "test_candidate.py", tmp_path / "candidate.json"
    assert cli.main(["codegen", "--from-log", str(path), "--run-id", "hand",
                     "--target", "python", "-o", str(output),
                     "--manifest", str(manifest)]) == 0
    ast.parse(output.read_text(encoding="utf-8"))
    saved = json.loads(manifest.read_text(encoding="utf-8"))
    assert saved["run_id"] == "hand" and saved["warnings"] == []

    with path.open("a", encoding="utf-8") as handle:
        handle.write(_line("u-1", 1, "AC_write", params={}).replace('"hand"', '"two"') + "\n")
    assert cli.main(["codegen", "--from-log", str(path)]) == 1
    assert "name one with run_id: hand, two" in capsys.readouterr().err
    assert cli.main(["codegen"]) == 1
    assert cli.main(["codegen", "x.json", "--from-log", str(path)]) == 1
    assert device_calls == []


def test_cli_script_codegen_keeps_its_default_style(tmp_path, capsys):
    script = tmp_path / "script.json"
    script.write_text(json.dumps([["AC_get_mouse_position"]]), encoding="utf-8")
    assert cli.main(["codegen", str(script)]) == 0
    assert "ac.get_mouse_position()" in capsys.readouterr().out


def test_executor_command_and_mcp_handler(tmp_path, device_calls):
    from je_auto_control.utils.executor.action_executor import _generate_code_from_journal
    from je_auto_control.utils.mcp_server.tools import _handlers_qa
    path = _write(tmp_path / "journal.jsonl",
                  _line("t-1", 1, "AC_write", params={"write_string": "hello"}))
    output = tmp_path / "out.py"
    result = _generate_code_from_journal(str(path), output=str(output))
    assert result["manifest"]["run_id"] == "hand" and result["observed_path_only"] is False
    assert output.read_text(encoding="utf-8") == result["code"]
    handled = _handlers_qa.generate_code_from_log(str(path), run_id="hand", target="robot")
    assert handled["actions"] == [["AC_write", {"write_string": "hello"}]]
    assert handled["manifest"]["validation"]["ast"] is None
    json.dumps(handled)
    assert device_calls == []
