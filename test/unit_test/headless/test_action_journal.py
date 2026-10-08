"""The structured action journal: what the executor writes at the action boundary.

Every test drives a private :class:`Executor` whose commands are fakes, so
nothing here reaches a mouse, a keyboard or a window.
"""
import json
import threading

import pytest

import je_auto_control as ac
from je_auto_control.utils.action_journal import recorder, store
from je_auto_control.utils.action_journal.events import (
    SCHEMA_VERSION, STATUS_ERROR, STATUS_INCOMPLETE, STATUS_OK, ActionEvent,
    JournalFormatError,
)
from je_auto_control.utils.action_journal.sanitize import REASON_MASKED, sanitise_params
from je_auto_control.utils.action_journal.store import (
    ActionJournal, list_journal_runs, load_journal, read_events,
)
from je_auto_control.utils.executor.action_executor import Executor

PASSWORD = "hunter2-Zq9!x"


@pytest.fixture(autouse=True)
def _journal_off():
    recorder.stop_action_journal()
    yield
    recorder.stop_action_journal()


@pytest.fixture()
def fake_executor():
    """A private executor with fake commands; ``calls`` lists what they received."""
    executor = Executor()
    calls = []

    def fake_step(**kwargs):
        calls.append(kwargs)
        return len(calls)

    def fake_fail(**kwargs):
        raise RuntimeError(f"login refused password={kwargs.get('password')}")

    def fake_interrupt():
        raise KeyboardInterrupt()

    executor.event_dict.update({
        "AC_fake_step": fake_step, "AC_fake_fail": fake_fail,
        "AC_fake_interrupt": fake_interrupt,
    })
    executor.calls = calls
    return executor


def _by_command(events, command):
    return [event for event in events if event.command == command]


def test_redaction_precedes_append(tmp_path, monkeypatch, fake_executor):
    path = tmp_path / "journal.jsonl"
    written = []
    real_append = store.append_json_line

    def spy(target, line):
        written.append(line)
        real_append(target, line)

    monkeypatch.setattr(store, "append_json_line", spy)
    password = PASSWORD
    fake_executor.variables.set("pw", password)
    recorder.start_action_journal(path, run_id="run-redact")
    fake_executor.execute_action([
        ["AC_fake_step", {"user": "ada", "password": password}],
        ["AC_fake_step", {"password": "${pw}"}],
        ["AC_loop", {"times": 1, "body": [
            ["AC_fake_step", {"smtp": {"token": password}}]]}],
        ["AC_fake_fail", {"password": password}],
    ])
    recorder.stop_action_journal()

    # The fakes did receive the real value: masking is the journal's doing.
    assert fake_executor.calls[0]["password"] == password
    assert fake_executor.calls[1]["password"] == password
    journal_text = path.read_text(encoding="utf-8")
    assert password not in journal_text
    # Not masked afterwards: no line handed to the file ever held it.
    assert written and all(password not in line for line in written)

    events = read_events(path)
    literal, reference = _by_command(events, "AC_fake_step")[:2]
    assert literal.params == {"user": "ada", "password": "***"}
    assert literal.unreplayable == {"params.password": REASON_MASKED}
    # A reference names the secret without holding it, so it stays replayable.
    assert reference.params == {"password": "${pw}"}
    assert reference.unreplayable == {}
    failed = _by_command(events, "AC_fake_fail")[0]
    assert failed.status == STATUS_ERROR and "RuntimeError" in failed.error


def test_parallel_parent_and_order(tmp_path, fake_executor):
    path = tmp_path / "journal.jsonl"
    run_id = recorder.start_action_journal(path)["run_id"]
    fake_executor.execute_action([
        ["AC_fake_step", {"n": 0}],
        ["AC_parallel", {"branches": [
            [["AC_fake_step", {"n": 10}], ["AC_fake_step", {"n": 11}]],
            [["AC_fake_step", {"n": 20}], ["AC_fake_step", {"n": 21}]],
        ]}],
    ])
    recorder.stop_action_journal()

    events = read_events(path, run_id=run_id)
    assert all(event.run_id == run_id for event in events)
    assert len(events) == 6
    parallel = _by_command(events, "AC_parallel")[0]
    assert parallel.parent_id is None and parallel.status == STATUS_OK
    for branch, expected in ((0, [10, 11]), (1, [20, 21])):
        steps = [event for event in events if event.branch == branch]
        assert [event.params["n"] for event in steps] == expected
        assert all(event.parent_id == parallel.step_id for event in steps)
        assert all(event.thread != parallel.thread for event in steps)
    # File order is start order: sequence rises with the lines.
    assert [event.sequence for event in events] == sorted(
        event.sequence for event in events)
    assert len({event.step_id for event in events}) == 6


def test_incomplete_step_stays_incomplete(tmp_path, fake_executor):
    path = tmp_path / "journal.jsonl"
    recorder.start_action_journal(path, run_id="run-cut")
    with pytest.raises(KeyboardInterrupt):
        fake_executor.execute_action([
            ["AC_fake_step", {"n": 1}],
            ["AC_loop", {"times": 1, "body": [["AC_fake_interrupt"]]}],
        ])
    recorder.stop_action_journal()
    events = read_events(path)
    unfinished = _by_command(events, "AC_fake_interrupt")[0]
    assert unfinished.status == 'incomplete'
    assert "KeyboardInterrupt" in unfinished.error
    assert _by_command(events, "AC_loop")[0].status == STATUS_INCOMPLETE
    assert _by_command(events, "AC_fake_step")[0].status == STATUS_OK

    # A process that died wrote no end line at all.
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [line for line in lines if json.loads(line)["record"] == "start"]
    path.write_text("\n".join(starts) + "\n", encoding="utf-8")
    assert {event.status for event in read_events(path)} == {STATUS_INCOMPLETE}
    assert all(event.finished_at is None for event in read_events(path))


def test_off_costs_one_shared_object_and_writes_nothing(tmp_path, fake_executor):
    first, second = recorder.step(["AC_fake_step"]), recorder.step(["AC_fake_step"])
    assert first is second is recorder._NULL
    assert recorder.current_step() is None
    fake_executor.execute_action([["AC_fake_step", {"n": 1}]])
    assert list(tmp_path.iterdir()) == []
    assert recorder.action_journal_status()["active"] is False


def test_nested_steps_keep_their_parent(tmp_path, fake_executor):
    path = tmp_path / "journal.jsonl"
    recorder.start_action_journal(path, session="device-7")
    fake_executor.execute_action([
        ["AC_loop", {"times": 2, "body": [
            ["AC_if_var", {"name": "missing", "op": "eq", "value": 1,
                           "else": [["AC_fake_step", {"n": 1}]]}]]}],
    ])
    recorder.stop_action_journal()
    events = read_events(path)
    loop = _by_command(events, "AC_loop")[0]
    branches = _by_command(events, "AC_if_var")
    assert [event.parent_id for event in branches] == [loop.step_id] * 2
    steps = _by_command(events, "AC_fake_step")
    assert [event.parent_id for event in steps] == [b.step_id for b in branches]
    assert all(event.session == "device-7" for event in events)
    # The outcome is described, never stored as a value that could be replayed.
    assert steps[0].outcome == {"type": "int", "value": 1}
    assert loop.params["body"][0][0] == "AC_if_var"


def test_outcome_text_and_unserialisable_arguments_are_not_stored(tmp_path, fake_executor):
    fake_executor.event_dict["AC_fake_read"] = lambda **_kwargs: PASSWORD
    path = tmp_path / "journal.jsonl"
    recorder.start_action_journal(path)
    fake_executor.execute_action([
        ["AC_fake_read", {"handle": object(), "point": (1, 2), "ratio": float("inf")}]])
    recorder.stop_action_journal()
    assert PASSWORD not in path.read_text(encoding="utf-8")
    event = read_events(path)[0]
    assert event.outcome == {"type": "str", "size": len(PASSWORD)}
    assert event.params["point"] == [1, 2]
    assert event.params["handle"] == {"$unserialisable": "object"}
    assert event.unreplayable["params.handle"] == "not JSON-serialisable (object)"
    assert "non-finite" in event.unreplayable["params.ratio"]


def test_vault_commands_mask_every_argument_but_keep_references():
    params, notes = sanitise_params("AC_secret_set", {"name": "db", "value": PASSWORD})
    assert params == {"name": "***", "value": "***"} and len(notes) == 2
    params, notes = sanitise_params("AC_write_secret", {"text": "${secrets.db}"})
    assert params == {"text": "${secrets.db}"} and notes == {}


def test_stopping_inside_a_script_still_ends_the_running_steps(tmp_path, fake_executor):
    path = tmp_path / "journal.jsonl"
    fake_executor.execute_action([
        ["AC_journal_start", {"path": str(path), "run_id": "in-script"}],
        ["AC_loop", {"times": 1, "body": [
            ["AC_fake_step", {"n": 1}], ["AC_journal_stop"],
            ["AC_fake_step", {"n": 2}]]}],
    ])
    events = read_events(path)
    assert [event.command for event in events] == [
        "AC_loop", "AC_fake_step", "AC_journal_stop"]
    assert {event.status for event in events} == {STATUS_OK}
    assert {event.run_id for event in events} == {"in-script"}


def test_executor_commands_read_and_list_runs(tmp_path, fake_executor):
    path = tmp_path / "journal.jsonl"
    for run in ("first", "second"):
        recorder.start_action_journal(path, run_id=run)
        fake_executor.execute_action(
            [["AC_fake_step", {"n": 1}], ["AC_fake_fail", {}]])
        assert recorder.action_journal_status()["events"] == 2
        recorder.stop_action_journal()
    record = fake_executor.execute_action([
        ["AC_journal_runs", {"path": str(path)}],
        ["AC_journal_read", {"path": str(path), "run_id": "second", "limit": 1}],
        ["AC_journal_status"],
    ])
    runs, tail, status = record.values()
    assert [run["run_id"] for run in runs] == ["first", "second"]
    assert runs[0]["events"] == 2 and runs[0]["ok"] == 1 and runs[0]["error"] == 1
    assert [event["command"] for event in tail] == ["AC_fake_fail"]
    assert status["active"] is False and status["last"]["run_id"] == "second"
    assert list_journal_runs(path) == runs


def test_starting_twice_is_refused(tmp_path):
    recorder.start_action_journal(tmp_path / "a.jsonl")
    with pytest.raises(ac.ActionJournalError):
        recorder.start_action_journal(tmp_path / "b.jsonl")
    assert isinstance(ac.ActionJournalError("x"), ac.AutoControlException)


def test_a_failed_write_stops_the_journal_not_the_run(tmp_path, monkeypatch, fake_executor):
    recorder.start_action_journal(tmp_path / "journal.jsonl")

    def broken(_target, _line):
        raise OSError("disk full")

    monkeypatch.setattr(store, "append_json_line", broken)
    record = fake_executor.execute_action(
        [["AC_fake_step", {"n": 1}], ["AC_fake_step", {"n": 2}]])
    assert list(record.values()) == [1, 2]
    status = recorder.action_journal_status()
    assert status["active"] is False and "disk full" in status["last"]["error"]


def test_reading_validates_the_schema_and_skips_torn_lines(tmp_path):
    path = tmp_path / "journal.jsonl"
    journal = ActionJournal(path)
    event = ActionEvent(run_id="r", step_id="s-1", sequence=1, command="AC_x")
    journal.append(event)
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"schema_version": 1, "record": "sta')  # a cut-off write
    journal.append(ActionEvent(run_id="r", step_id="s-2", sequence=2, command="AC_y"))
    contents = load_journal(path)
    assert [item.step_id for item in contents.events] == ["s-1", "s-2"]
    assert contents.torn_lines == (2,) and contents.lines == {"s-1": 1, "s-2": 3}
    assert journal.read(run_id="other") == []
    assert event.schema_version == SCHEMA_VERSION == 1

    for bad in ({"schema_version": 2, "run_id": "r", "step_id": "s"},
                {"schema_version": 1, "run_id": "r", "step_id": "s-9",
                 "sequence": 1, "command": 7},
                {"schema_version": 1, "run_id": "r", "step_id": "s-1",
                 "sequence": 1, "command": "AC_x"},
                {"schema_version": 1, "run_id": "r", "step_id": "s-8",
                 "sequence": 1, "command": "AC_x", "status": "fine"},
                ["not", "an", "object"]):
        broken = tmp_path / "broken.jsonl"
        broken.write_text(path.read_text(encoding="utf-8") + json.dumps(bad) + "\n",
                          encoding="utf-8")
        with pytest.raises(JournalFormatError):
            read_events(broken)
    with pytest.raises(JournalFormatError):
        read_events(tmp_path / "absent.jsonl")


def test_concurrent_top_level_runs_share_one_ordered_file(tmp_path, fake_executor):
    path = tmp_path / "journal.jsonl"
    recorder.start_action_journal(path)

    def run(offset):
        Executor.execute_action(
            fake_executor, [["AC_fake_step", {"n": offset + i}] for i in range(20)])

    threads = [threading.Thread(target=run, args=(offset,)) for offset in (0, 100, 200)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    recorder.stop_action_journal()
    events = read_events(path)
    assert len(events) == 60 and {event.status for event in events} == {STATUS_OK}
    assert [event.sequence for event in events] == list(range(1, 61))


def test_every_surface_is_wired():
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    commands = {"AC_journal_start", "AC_journal_stop", "AC_journal_status",
                "AC_journal_read", "AC_journal_runs", "AC_generate_code_from_journal"}
    assert commands <= ac.executor.known_commands()
    assert commands <= set(COMMAND_SPECS)
    tools = {tool.name for tool in build_default_tool_registry()}
    assert {"ac_journal_start", "ac_journal_stop", "ac_journal_status",
            "ac_journal_read", "ac_journal_runs", "ac_generate_code_from_log"} <= tools
    for name in ("ActionEvent", "ActionJournal", "read_events", "start_action_journal",
                 "stop_action_journal", "action_journal_status", "list_journal_runs",
                 "JournalFormatError", "ActionJournalError"):
        assert name in ac.__all__ and hasattr(ac, name)
