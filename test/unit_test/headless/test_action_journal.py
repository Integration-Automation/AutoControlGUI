"""Versioned journal storage never persists secrets or upgrades unfinished steps."""
import json
import multiprocessing
import threading
from dataclasses import FrozenInstanceError, replace

import pytest

from je_auto_control.utils.action_journal import ActionEvent, ActionJournal, ActionJournalError, read_events


def _event(**changes):
    event = ActionEvent(run_id="run", step_id="step", command="AC_probe",
                        parameters={"value": "input"}, started_at=1.0)
    return replace(event, **changes)


def test_event_is_frozen_and_unfinished_is_not_success(tmp_path):
    event = _event()
    with pytest.raises(FrozenInstanceError):
        event.status = "ok"
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(event)
    loaded = read_events(journal.path)
    assert loaded[0].status == "incomplete" and loaded[0].finished_at is None
    assert loaded[0].schema_version == 1 and loaded[0].sequence == 1


def test_redaction_precedes_append_and_keeps_secret_references(tmp_path, monkeypatch):
    from je_auto_control.utils.action_journal import store
    seen = []
    original = store.append_json_line

    def append(path, line):
        seen.append(line)
        assert "literal-password" not in line and "literal-token" not in line
        original(path, line)

    monkeypatch.setattr(store, "append_json_line", append)
    journal = ActionJournal(tmp_path / "events.jsonl")
    event = _event(parameters={"password": "literal-password", "headers": {"Authorization": "literal-token"},
                               "text": "${secrets.LOGIN}"})
    journal.append(event)
    assert seen and "${secrets.LOGIN}" in seen[0]
    assert event.parameters["password"] == "literal-password"
    assert read_events(journal.path)[0].parameters["password"] == "***"


def test_secret_command_outcome_and_error_are_not_persisted(tmp_path):
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event(command="AC_secret_set", parameters={"name": "login", "value": "hidden"},
                          outcome={"echo": "hidden"}, error="hidden in error",
                          status="error", finished_at=2.0))
    assert "hidden" not in journal.path.read_text(encoding="utf-8")
    event = read_events(journal.path)[0]
    assert event.outcome == "***" and event.error == "***"
    assert event.non_replayable


def test_sensitive_input_is_also_masked_from_echoed_outcomes_and_errors(tmp_path):
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event(parameters={"password": "never-persist-this"},
                          outcome={"message": "echo never-persist-this"}, error="bad never-persist-this",
                          status="error", finished_at=2.0))
    assert "never-persist-this" not in journal.path.read_text(encoding="utf-8")


def test_opaque_outcome_keys_cannot_leak_credentials(tmp_path):
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event(outcome={"private-result": {"another-credential": "anything"}},
                          status="ok", finished_at=2.0))
    text = journal.path.read_text(encoding="utf-8")
    assert "private-result" not in text and "another-credential" not in text
    event = read_events(journal.path)[0]
    assert "redacted_outcome" in event.non_replayable and event.outcome_type == "object"


def test_sensitive_fields_can_retain_explicit_secret_references(tmp_path):
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event(parameters={"token": "${secrets.LOGIN}", "password": "secret://LOGIN"}))
    assert read_events(journal.path)[0].parameters == {"token": "${secrets.LOGIN}", "password": "secret://LOGIN"}


def test_nested_secret_actions_mask_even_nonstandard_argument_shapes(tmp_path):
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event(parameters={"body": [["AC_secret_unlock", "private-passphrase"]]}))
    assert "private-passphrase" not in journal.path.read_text(encoding="utf-8")


def test_cycles_and_nonfinite_payloads_get_non_replayable_markers(tmp_path):
    cycle = []
    cycle.append(cycle)
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event(parameters={"cycle": cycle, "number": float("nan")}))
    assert {"cyclic_payload", "nonfinite_number"} <= set(read_events(journal.path)[0].non_replayable)


def test_unknown_payload_is_not_serialized_using_repr(tmp_path):
    class Payload:
        def __repr__(self):
            raise AssertionError("must never inspect arbitrary repr")

    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event(parameters={"payload": Payload()}))
    event = read_events(journal.path)[0]
    assert event.non_replayable and "unsupported" in str(event.parameters)


def test_run_filter_and_parent_links_survive_round_trip(tmp_path):
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event(step_id="parent"))
    journal.append(_event(step_id="child", parent_id="parent"))
    journal.append(_event(run_id="another", step_id="foreign"))
    events = read_events(journal.path, run_id="run")
    assert [event.step_id for event in events] == ["parent", "child"]
    assert events[1].parent_id == "parent"
    assert [event.sequence for event in read_events(journal.path)] == [1, 2, 3]


def test_parallel_writers_share_one_order_even_across_instances(tmp_path):
    path = tmp_path / "events.jsonl"
    barrier = threading.Barrier(4, timeout=5)
    failures = []

    def write(index):
        try:
            journal = ActionJournal(path)
            barrier.wait()
            for step in range(8):
                journal.append(_event(step_id=f"{index}-{step}", parent_id="parent"))
        except Exception as error:  # reason: surface worker failures on the test thread
            failures.append(error)

    threads = [threading.Thread(target=write, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert not any(thread.is_alive() for thread in threads) and failures == []
    events = read_events(path)
    assert len(events) == 32 and [event.sequence for event in events] == list(range(1, 33))
    assert all(event.run_id == "run" and event.parent_id == "parent" for event in events)


def test_partial_tail_does_not_complete_a_step_and_append_recovers_it(tmp_path):
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event())
    with journal.path.open("ab") as handle:
        handle.write(b'{"schema_version":1,"status":"ok"')
    assert read_events(journal.path)[0].status == "incomplete"
    journal.append(_event(status="ok", finished_at=2.0))
    events = read_events(journal.path)
    assert [event.status for event in events] == ["incomplete", "ok"]
    assert [event.sequence for event in events] == [1, 2]


@pytest.mark.parametrize("change", [
    {"schema_version": 2}, {"run_id": ""}, {"step_id": ""}, {"command": ""},
    {"status": "success-ish"}, {"status": "ok"}, {"finished_at": 0.0, "status": "ok"},
    {"started_at": float("nan")}, {"sequence": -1},
    {"started_at": 10 ** 400}, {"sequence": 2 ** 63}, {"parent_id": "step"},
    {"started_at": True}, {"parameters": []}, {"non_replayable": "reason"},
])
def test_invalid_events_fail_before_any_write(tmp_path, change):
    journal = ActionJournal(tmp_path / "events.jsonl")
    with pytest.raises(ActionJournalError):
        journal.append(_event(**change))
    assert not journal.path.exists()


@pytest.mark.parametrize("change", [
    {"schema_version": 2}, {"extra": "unknown"}, {"sequence": True}, {"sequence": 0},
])
def test_reader_refuses_unknown_schema_and_fields(tmp_path, change):
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event())
    row = json.loads(journal.path.read_text(encoding="utf-8"))
    row.update(change)
    journal.path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ActionJournalError):
        read_events(journal.path)


def test_missing_journal_is_empty_and_malformed_complete_line_is_refused(tmp_path):
    path = tmp_path / "events.jsonl"
    assert read_events(path) == []
    path.write_text('{"bad":\n', encoding="utf-8")
    with pytest.raises(ActionJournalError):
        read_events(path)


def test_control_characters_cannot_hide_a_corrupt_complete_record(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_bytes(b'\rnot-json\n')
    with pytest.raises(ActionJournalError):
        read_events(path)


def test_reader_checks_sequence_even_for_runs_it_filters_out(tmp_path):
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event())
    row = json.loads(journal.path.read_text(encoding="utf-8"))
    row["run_id"] = "other"
    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    with pytest.raises(ActionJournalError, match="unordered"):
        read_events(journal.path, run_id="run")


@pytest.mark.parametrize("value", ["\ud800", 10 ** 5000], ids=["invalid-unicode", "oversized-integer"])
def test_invalid_json_encodings_are_framework_errors_before_write(tmp_path, value):
    journal = ActionJournal(tmp_path / "events.jsonl")
    with pytest.raises(ActionJournalError, match="encoding"):
        journal.append(_event(parameters={"value": value}))
    assert not journal.path.exists()


def test_sequence_exhaustion_does_not_append_an_unreadable_record(tmp_path):
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event())
    row = json.loads(journal.path.read_text(encoding="utf-8"))
    row["sequence"] = 2 ** 63 - 1
    journal.path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ActionJournalError):
        journal.append(_event())
    assert len(read_events(journal.path)) == 1


def test_large_rows_and_a_partial_tail_recover_across_chunk_boundaries(tmp_path):
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event(parameters={"text": "多語系" * 4000}))
    with journal.path.open("ab") as handle:
        handle.write(b'{"partial":' + b"x" * 9000)
    journal.append(_event(step_id="next"))
    assert [event.sequence for event in read_events(journal.path)] == [1, 2]


def _process_append(path, ready, start, index):
    journal = ActionJournal(path)
    ready.set()
    if not start.wait(timeout=15):
        raise RuntimeError("journal worker was never released")
    for step in range(12):
        journal.append(_event(step_id=f"process-{index}-{step}"))


def test_processes_share_a_monotonic_append_order(tmp_path):
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    ready = [context.Event(), context.Event()]
    path = tmp_path / "events.jsonl"
    processes = [context.Process(target=_process_append, args=(path, ready[index], start, index))
                 for index in range(2)]
    try:
        for process in processes:
            process.start()
        assert all(event.wait(timeout=15) for event in ready)
        start.set()
        for process in processes:
            process.join(timeout=20)
            assert process.exitcode == 0
    finally:
        start.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            process.close()
    assert [event.sequence for event in read_events(path)] == list(range(1, 25))


def test_record_budget_uses_encoded_bytes_and_fails_before_write(tmp_path):
    journal = ActionJournal(tmp_path / "events.jsonl")
    with pytest.raises(ActionJournalError, match="8 MiB"):
        journal.append(_event(parameters={"text": "界" * 3_000_000}))
    assert not journal.path.exists()


@pytest.mark.parametrize("operation", ["read", "append"])
def test_storage_errors_stay_in_the_framework_exception_family(tmp_path, operation):
    destination = tmp_path / "directory"
    destination.mkdir()
    with pytest.raises(ActionJournalError):
        if operation == "read":
            read_events(destination)
        else:
            ActionJournal(destination).append(_event())


@pytest.mark.parametrize("existing", [
    b"unrelated user content",
    b'{"users":[{"name":"local"}]}',
    b'{\n  "users": [\n    "local"\n  ]\n}',
    b'ordinary text\npartial tail',
    b'{"schema_version":1,"run_id":"partial-first-record"',
])
def test_append_never_truncates_an_existing_nonjournal_destination(tmp_path, existing):
    journal = ActionJournal(tmp_path / "existing.jsonl")
    journal.path.write_bytes(existing)
    with pytest.raises(ActionJournalError):
        journal.append(_event())
    assert journal.path.read_bytes() == existing
    with pytest.raises(ActionJournalError):
        read_events(journal.path)


def test_corrupt_complete_record_prevents_torn_tail_repair(tmp_path):
    journal = ActionJournal(tmp_path / "events.jsonl")
    journal.append(_event())
    with journal.path.open("ab") as handle:
        handle.write(b'{not-json}\npartial')
    original = journal.path.read_bytes()
    with pytest.raises(ActionJournalError):
        journal.append(_event())
    assert journal.path.read_bytes() == original


def test_foreign_destination_reports_the_format_refusal(tmp_path):
    journal = ActionJournal(tmp_path / "existing.jsonl")
    journal.path.write_bytes(b"unrelated user content")
    with pytest.raises(ActionJournalError, match="destination has no committed journal"):
        journal.append(_event())
