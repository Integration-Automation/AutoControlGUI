"""Secret-named fields of a command's result are masked at any depth, by one rule.

The Script Builder masked only the top-level fields of the commands its schema
marks ``sensitive_result``: ``AC_lease_secret`` and ``AC_lease_active`` (lease
tokens, the latter nested under ``leases``) and ``AC_rest_api_start`` /
``AC_rest_api_status`` (the shared REST bearer token; no schema entry) were
printed in plain text. ``redact_result`` is now the rule for the executor's
result log and for the builder's result pane alike, and ``masked_fields``
lists exactly what it masks -- which is what the builder offers once.

An identifier with a secret-looking name stays readable where a person reads
their own run: ``AC_approval_request``'s ``token`` is the request id the maker
hands to the checker.

No server is started: the REST registry is replaced by a fake.
"""
import copy
import json
import logging

import pytest

from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
from je_auto_control.gui.script_builder.step_model import OneTimeCollector, displayable_record
from je_auto_control.utils.executor import action_executor
from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.executor.action_redaction import (
    RESULT_IDENTIFIERS, SENSITIVE_ARGUMENT_NAMES, MaskedField, masked_fields, record_command,
    redact_actions, redact_result,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_BEARER = "shared-rest-bearer-0123456789"
_DEEP = {
    "running": True,
    "token": "t-top",
    "leases": [{"token": "t-a", "name": "db"}, {"Token": "t-b", "name": "api"}],
    "http": {"headers": {"Set-Cookie": "sid=1", "Content-Type": "text/plain"}},
    "pairs": ({"password": "p-1"}, {"note": "plain"}),
    "empty": {"token": None, "secret": ""},
    "secret": {"whole": ["mapping", 1]},
}


def _collected(actions: list):
    collector = OneTimeCollector()
    record = execute_action(actions, result_callback=collector.note)
    return record, collector.take()[0]


def _logged_run(caplog, actions: list):
    autocontrol_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=autocontrol_logger.name):
            record = execute_action(actions)
    finally:
        autocontrol_logger.removeHandler(caplog.handler)
    return record, "\n".join(entry.getMessage() for entry in caplog.records)


# --- the rule ----------------------------------------------------------------


def test_a_secret_named_field_is_masked_at_any_depth_for_any_command():
    before = copy.deepcopy(_DEEP)
    shown = redact_result("AC_anything", _DEEP)
    assert _DEEP == before, "the result is not changed"
    assert shown["token"] == "***" and shown["running"] is True
    assert shown["leases"] == [{"token": "***", "name": "db"}, {"Token": "***", "name": "api"}]
    assert shown["http"]["headers"] == {"Set-Cookie": "***", "Content-Type": "text/plain"}
    assert shown["pairs"] == [{"password": "***"}, {"note": "plain"}]
    assert shown["secret"] == "***", "a secret-named container is masked whole"
    assert shown["empty"] == {"token": None, "secret": ""}, "an empty field has nothing to hide"
    assert redact_result(None, _DEEP) == shown, "the command plays no part without an identifier list"
    for plain in ("just text", 5, None, ["a", 1]):
        assert redact_result("AC_anything", plain) == plain


def test_masked_fields_are_exactly_what_the_rule_masks():
    found = masked_fields("AC_anything", _DEEP)
    assert [(field.path, field.value) for field in found] == [
        (("token",), "t-top"),
        (("leases", 0, "token"), "t-a"),
        (("leases", 1, "Token"), "t-b"),
        (("http", "headers", "Set-Cookie"), "sid=1"),
        (("pairs", 0, "password"), "p-1"),
        (("secret",), {"whole": ["mapping", 1]}),
    ]
    shown = redact_result("AC_anything", _DEEP)
    assert json.dumps(shown).count('"***"') == len(found)
    for field in found:
        holder = shown
        for part in field.path[:-1]:
            holder = holder[part]
        assert holder[field.path[-1]] == "***"
    assert "t-top" not in repr(found) + str(found[0]), "a masked field never prints its value"
    assert isinstance(found[0], MaskedField)


def test_a_record_nested_in_a_result_is_masked_per_command_and_an_action_as_an_action():
    result = {
        "execute: ['AC_approval_request', {'action': 'x'}]": {"token": "req-1"},
        "execute: ['AC_user_add', {'user_id': 'a'}]": {"user_id": "a", "token": "tok-1"},
        "plan": ["AC_secret_set", {"name": "db", "value": "hunter2"}],
    }
    assert redact_result("AC_execute_action", result) == {
        "execute: ['AC_approval_request', {'action': 'x'}]": {"token": "***"},
        "execute: ['AC_user_add', {'user_id': 'a'}]": {"user_id": "a", "token": "***"},
        "plan": redact_actions(result["plan"]),
    }
    shown = redact_result("AC_execute_action", result, show_identifiers=True)
    assert shown["execute: ['AC_approval_request', {'action': 'x'}]"] == {"token": "req-1"}
    assert shown["execute: ['AC_user_add', {'user_id': 'a'}]"]["token"] == "***"
    assert "hunter2" not in json.dumps(shown)
    assert [field.value for field in masked_fields(
        "AC_execute_action", result, show_identifiers=True)] == ["tok-1"]


def test_record_command_reads_the_command_of_a_record_key():
    assert record_command("execute: ['AC_lease_active']") == "AC_lease_active"
    assert record_command("dry-run: ['AC_user_add', {'user_id': 'a'}]") == "AC_user_add"
    for key in ("token", "execute: nothing", 5, None):
        assert record_command(key) is None


# --- identifiers -------------------------------------------------------------


def test_the_identifier_list_is_explicit_and_holds_only_the_approval_request_id():
    assert dict(RESULT_IDENTIFIERS) == {"AC_approval_request": frozenset({"token"})}
    with pytest.raises(TypeError):
        RESULT_IDENTIFIERS["AC_user_add"] = frozenset({"token"})  # type: ignore[index]
    for names in RESULT_IDENTIFIERS.values():
        assert names <= SENSITIVE_ARGUMENT_NAMES, "an entry only exempts a name the rule would mask"


def test_an_identifier_is_shown_only_at_the_top_of_its_own_command_result():
    result = {"token": "req-1", "detail": {"token": "inner"}}
    assert redact_result("AC_approval_request", result, show_identifiers=True) == {
        "token": "req-1", "detail": {"token": "***"}}
    assert redact_result("AC_approval_request", result) == {"token": "***", "detail": {"token": "***"}}
    assert redact_result("AC_lease_secret", {"token": "lease"}, show_identifiers=True) == {"token": "***"}
    assert masked_fields("AC_approval_request", {"token": "req-1"}, show_identifiers=True) == []


def test_the_approval_request_id_is_readable_in_the_builder_and_not_offered(tmp_path, caplog):
    db = str(tmp_path / "approvals.json")
    actions = [["AC_approval_request", {"action": "wire transfer", "requester": "maker", "db": db}]]
    record, values = _collected(actions)
    request_id = list(record.values())[0]["token"]
    assert request_id in json.dumps(displayable_record(record)), "the maker can read the id"
    assert values == [], "it is not a one-time value"
    approved = execute_action([["AC_approval_approve", {"token": request_id, "approver": "checker", "db": db}]])
    assert list(approved.values())[0] == {"approved": True}, "the id shown is the one the checker uses"
    record, logged = _logged_run(caplog, actions)
    assert "AC_approval_request" in logged and list(record.values())[0]["token"] not in logged, \
        "the log keeps masking it: the exemption is for the person reading their own run"


# --- the commands that were printed in plain text ----------------------------


def test_a_lease_token_is_masked_in_the_builder_and_offered_once():
    record, values = _collected([["AC_lease_secret", {"name": "redaction-db", "ttl": 5}],
                                 ["AC_lease_active"]])
    issued, active = record.values()
    try:
        shown = displayable_record(record)
        text = json.dumps(shown, default=str)
        assert issued["token"] not in text and "redaction-db" in text
        assert list(shown.values())[0] == {"token": "***", "ttl": 5.0}
        mine = [lease for lease in list(shown.values())[1]["leases"] if lease["name"] == "redaction-db"]
        assert mine and all(lease["token"] == "***" for lease in mine)
        assert (values[0].command, values[0].subject, values[0].name, values[0].value) == (
            "AC_lease_secret", "redaction-db", "token", issued["token"])
        listed = [value for value in values[1:] if value.subject == "redaction-db"]
        assert [(value.command, value.value) for value in listed] == [("AC_lease_active", issued["token"])]
        assert listed[0].name.startswith("leases[") and listed[0].name.endswith("].token")
        assert text.count('"***"') == len(values), "what is offered is exactly what is masked"
    finally:
        execute_action([["AC_revoke_lease", {"token": issued["token"]}]])


@pytest.mark.parametrize("command", ["AC_rest_api_start", "AC_rest_api_status"])
def test_the_shared_rest_bearer_token_is_masked_although_the_command_has_no_schema_entry(
        monkeypatch, caplog, command):
    status = {"running": True, "host": "127.0.0.1", "port": 9939, "token": _BEARER,
              "url": "http://127.0.0.1:9939"}
    monkeypatch.setattr(action_executor.rest_api_registry, "start", lambda **_kwargs: dict(status))
    monkeypatch.setattr(action_executor.rest_api_registry, "status", lambda: dict(status))
    assert command not in COMMAND_SPECS, "it is run from a loaded action file, like every server command"
    autocontrol_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=autocontrol_logger.name):
            record, values = _collected([[command]])
    finally:
        autocontrol_logger.removeHandler(caplog.handler)
    assert list(record.values())[0]["token"] == _BEARER, "the script still receives it"
    shown = list(displayable_record(record).values())[0]
    assert shown == {**status, "token": "***"}
    assert [(value.command, value.name, value.value) for value in values] == [(command, "token", _BEARER)]
    assert _BEARER not in "\n".join(entry.getMessage() for entry in caplog.records)


def test_a_stopped_rest_server_has_no_token_to_mask_or_offer(monkeypatch):
    monkeypatch.setattr(action_executor.rest_api_registry, "status",
                        lambda: {"running": False, "token": None, "url": None})
    record, values = _collected([["AC_rest_api_status"]])
    assert list(displayable_record(record).values())[0] == {"running": False, "token": None, "url": None}
    assert values == []


def test_the_commands_that_answer_with_a_generated_secret_are_marked_in_the_schema():
    marked = {command for command, spec in COMMAND_SPECS.items() if spec.sensitive_result}
    assert marked == {"AC_user_add", "AC_user_rotate_token", "AC_jwt_encode",
                      "AC_lease_secret", "AC_lease_active"}
    assert not marked & set(RESULT_IDENTIFIERS), "a command is one or the other"
    for command in ("AC_lease_secret", "AC_lease_active"):
        assert "One-time values" in COMMAND_SPECS[command].description
    assert "not masked" in COMMAND_SPECS["AC_approval_request"].description


def test_the_display_of_a_record_does_not_depend_on_the_schema_flag():
    record = {
        "execute: ['AC_made_up_command']": {"items": [{"api_key": "k-1", "id": 7}]},
        "execute: ['AC_get_var', {'name': 'a'}]": "AutoControlActionException('token missing')",
        "execute: ['AC_loop', {'times': 2}]": 2,
    }
    assert displayable_record(record) == {
        "execute: ['AC_made_up_command']": {"items": [{"api_key": "***", "id": 7}]},
        "execute: ['AC_get_var', {'name': 'a'}]": "AutoControlActionException('token missing')",
        "execute: ['AC_loop', {'times': 2}]": 2,
    }
    assert displayable_record("not a record") == "not a record"
    assert displayable_record([{"token": "t"}]) == [{"token": "***"}]
