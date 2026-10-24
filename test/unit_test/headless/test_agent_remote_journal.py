"""Remote ownership cannot be released by a local-only witness or stale protocol event."""
import json

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.input_journal import InputJournal
from je_auto_control.utils.agent_runtime.remote_journal import RemoteInputJournal, device_identity, device_resource

DEVICE = device_identity("android", "reviewed-device-1")


@pytest.fixture
def journal(tmp_path):
    guard = RemoteInputJournal(tmp_path / "device.lock", DEVICE)
    guard.acquire()
    guard.update({}, "perform")
    return guard


def event(journal, kind="remote_begin", **changes):
    return {"kind": kind, "controller": journal.owner, "device": DEVICE,
            "sequence": journal.sequence, "epoch": "before-retirement", **changes}


def test_settled_events_advance_sequence_without_persisting_tool_arguments(journal):
    begin = event(journal)
    journal.consume(begin)
    assert journal.read()["remote_effect"] == begin
    journal.update({}, "perform")
    assert journal.read()["remote_effect"] == begin
    journal.consume(event(journal, "remote_end"))
    assert journal.sequence == 2
    journal.release()
    assert journal.read()["owner"] is None
    assert not journal.pending


@pytest.mark.parametrize("change", [
    {"controller": "another-controller"}, {"sequence": True}, {"sequence": 0}, {"sequence": 2},
    {"epoch": ""}, {"epoch": "epoch\n"}, {"device": {**DEVICE, "physical_id": "other-device"}},
    {"arguments": "must-not-be-written"}, {"kind": "key_press"}, {"kind": []},
])
def test_bad_events_never_change_durable_state(journal, change):
    before = journal.path.read_bytes()
    with pytest.raises(AgentTaskError):
        journal.consume(event(journal, **change))
    assert journal.path.read_bytes() == before


def test_duplicate_begin_and_unmatched_end_keep_quarantine(journal):
    with pytest.raises(AgentTaskError):
        journal.consume(event(journal, "remote_end"))
    journal.consume(event(journal))
    for proposal in (event(journal), event(journal, "remote_end", epoch="different")):
        with pytest.raises(AgentTaskError):
            journal.consume(proposal)
    with pytest.raises(AgentTaskError, match="quarantined"):
        journal.release()
    assert journal.read()["remote_effect"] is not None


@pytest.mark.parametrize("operation", [None, "observe", "configure"])
def test_pending_effect_cannot_lose_its_operation_marker(journal, operation):
    journal.consume(event(journal))
    before = journal.path.read_bytes()
    with pytest.raises(AgentTaskError, match="settle"):
        journal.update({}, operation)
    assert journal.path.read_bytes() == before


@pytest.mark.parametrize("operation", [None, "observe", "configure"])
def test_read_only_operations_cannot_authorize_effects(journal, operation):
    journal.update({}, operation)
    with pytest.raises(AgentTaskError, match="perform"):
        journal.consume(event(journal))


def test_recovery_baseline_is_after_retirement_not_the_input_epoch(journal):
    journal.consume(event(journal))
    epoch = ["already-reconnected-before-retirement"]
    proof = lambda: {"device": DEVICE, "epoch": epoch[0], "writers_retired": True}
    assert journal.recover("review first", proof, "admin") == {
        "recovered": False, "phase": "awaiting_new_device_epoch"}
    assert journal.read()["recovery_epoch"] == epoch[0]
    assert not journal.recover("still the same generation", proof, "admin")["recovered"]
    epoch[0] = "new-device-generation-invalidates-old-commands"
    assert journal.recover("reviewed reset", proof, "admin")["recovered"]
    assert journal.read()["remote_effect"] is None
    assert journal.read()["review"]["note"] == "reviewed reset"


@pytest.mark.parametrize("evidence", [None, {}, {"device": DEVICE, "epoch": "new", "writers_retired": 1},
    {"device": {**DEVICE, "platform": "ios"}, "epoch": "new", "writers_retired": True},
    {"device": DEVICE, "epoch": "new", "writers_retired": False},
    {"device": DEVICE, "epoch": "", "writers_retired": True}])
def test_untrusted_or_incomplete_recovery_evidence_never_clears_effect(journal, evidence):
    journal.consume(event(journal))
    before = journal.path.read_bytes()
    with pytest.raises(AgentTaskError):
        journal.recover("review", lambda: evidence, "admin")
    assert journal.path.read_bytes() == before


def test_remote_witness_blocks_other_owners_and_generic_local_recovery(journal):
    journal.consume(event(journal))
    resource = journal.path.with_suffix("")
    with pytest.raises(AgentTaskError, match="recovery"):
        RemoteInputJournal(resource, DEVICE).acquire()
    local = InputJournal(resource)
    with pytest.raises(AgentTaskError, match="device-specific"):
        local.acquire()
    with pytest.raises(AgentTaskError, match="device-specific"):
        local.recover("cannot clear remote", lambda: None, "admin")


@pytest.mark.parametrize("field,value", [("remote_protocol", True), ("next_sequence", False),
    ("next_sequence", 0), ("in_flight", []), ("remote_device", {}), ("remote_effect", {}),
    ("recovery_epoch", "orphaned-baseline"), ("unexpected", True)])
def test_corrupt_or_redirected_witness_is_never_acquired(journal, field, value):
    data = journal.read()
    data[field] = value
    journal.path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AgentTaskError):
        RemoteInputJournal(journal.path.with_suffix(""), DEVICE).acquire()


def test_identity_is_physical_not_endpoint_app_or_profile():
    assert device_resource(DEVICE) == device_resource(dict(DEVICE))
    assert device_resource(DEVICE) != device_resource({**DEVICE, "platform": "ios"})
    assert device_resource(DEVICE) != device_resource({**DEVICE, "physical_id": "reviewed-device-2"})


@pytest.mark.parametrize("identity", ["", "device with spaces", "x" * 257, "secret\n", "裝置"])
def test_ambiguous_device_tokens_are_refused(identity):
    with pytest.raises(AgentTaskError):
        device_identity("android", identity)
