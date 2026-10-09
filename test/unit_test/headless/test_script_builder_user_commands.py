"""The Script Builder knows the ``AC_user_*`` commands, and never shows a token.

The five RBAC user-management commands had no schema, so the builder offered
them only through the raw JSON view. Two of them answer with the user's
bearer token -- the one time it exists outside its hash -- and the builder
prints a run's whole record into its result pane, so those two are marked and
the record is masked before it is displayed.

Headless: the schema and the masking are plain data and functions; the last
test builds the tab offscreen and runs against a fake executor.
"""
import inspect
import json

import pytest

from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS, FieldType
from je_auto_control.gui.script_builder.step_model import (
    HIDDEN_RESULT, Step, displayable_record, steps_to_actions,
)
from je_auto_control.utils.executor.action_executor import execute_action, executor
from je_auto_control.utils.rbac import Role, UserStore

_USER_COMMANDS = ("AC_user_add", "AC_user_remove", "AC_user_set_role",
                  "AC_user_rotate_token", "AC_user_list")
_TOKEN_COMMANDS = {"AC_user_add", "AC_user_rotate_token"}


@pytest.mark.parametrize("command", _USER_COMMANDS)
def test_every_user_command_has_a_schema_entry_matching_the_executor(command):
    spec = COMMAND_SPECS[command]
    assert spec.category == "Security" and spec.description
    accepted = inspect.signature(executor.event_dict[command]).parameters
    assert [field.name for field in spec.fields if field.name not in accepted] == []
    required = {name for name, parameter in accepted.items()
                if parameter.default is inspect.Parameter.empty}
    assert required == {field.name for field in spec.fields if not field.optional}


def test_role_fields_offer_exactly_the_three_roles():
    for command in ("AC_user_add", "AC_user_set_role"):
        role = next(field for field in COMMAND_SPECS[command].fields if field.name == "role")
        assert role.field_type is FieldType.ENUM and list(role.choices) == Role.all()


def test_only_the_token_returning_commands_are_marked():
    marked = {command for command, spec in COMMAND_SPECS.items() if spec.sensitive_result}
    # AC_jwt_encode and the lease commands answer with a credential the same way.
    assert marked == _TOKEN_COMMANDS | {"AC_jwt_encode", "AC_lease_secret", "AC_lease_active"}


def test_a_run_record_is_shown_without_the_token(tmp_path):
    users = str(tmp_path / "users.json")
    actions = steps_to_actions([
        Step("AC_user_add", {"user_id": "ann", "role": "operator", "users_path": users}),
        Step("AC_user_rotate_token", {"user_id": "ann", "users_path": users}),
        Step("AC_user_list", {"users_path": users}),
    ])
    record = execute_action(actions)
    tokens = [value["token"] for value in record.values() if isinstance(value, dict)
              and "token" in value]
    assert len(tokens) == 2 and all(len(token) > 20 for token in tokens)
    shown = json.dumps(displayable_record(record), default=str)
    assert not any(token in shown for token in tokens)
    assert "ann" in shown and "operator" in shown, "everything but the token stays readable"
    assert UserStore(users).authenticate(tokens[1]).user_id == "ann", "the record itself is intact"


def test_a_block_does_not_surface_the_nested_token_at_all(tmp_path):
    """A block's record is its own summary; the nested command's reply is not in it."""
    users = str(tmp_path / "users.json")
    record = execute_action([["AC_loop", {"times": 1, "body": [
        ["AC_user_add", {"user_id": "bob", "users_path": users}]]}]])
    assert UserStore(users).get("bob") is not None
    assert "token" not in json.dumps(displayable_record(record), default=str).replace(
        "rotate_token", "")


def test_a_marked_result_inside_a_nested_record_is_masked():
    nested = {"execute: ['AC_try', {}]": {"body": [
        {"execute: ['AC_user_add', {'user_id': 'x'}]": {"user_id": "x", "token": "tok-value"}}]}}
    shown = json.dumps(displayable_record(nested))
    assert "tok-value" not in shown and '"user_id": "x"' in shown


def test_a_marked_command_answering_with_something_else_is_hidden_whole():
    record = {"execute: ['AC_user_add', {'user_id': 'x'}]": ["opaque", "values"],
              "execute: ['AC_user_list']": [{"user_id": "x"}]}
    shown = displayable_record(record)
    assert shown["execute: ['AC_user_add', {'user_id': 'x'}]"] == HIDDEN_RESULT
    assert shown["execute: ['AC_user_list']"] == [{"user_id": "x"}]


def test_a_failed_marked_command_still_shows_its_error():
    key = "execute: ['AC_user_rotate_token', {'user_id': 'nobody'}]"
    assert displayable_record({key: "UserAuthError('unknown user')"})[key].startswith("UserAuthError")


def test_a_secret_named_field_is_masked_for_a_command_that_is_not_marked():
    """Only marked commands were masked, so a lease or REST bearer token was printed."""
    key = "execute: ['AC_get_var', {'name': 'token'}]"
    record = {key: {"token": "masked whatever the command", "count": 3}}
    assert displayable_record(record) == {key: {"token": "***", "count": 3}}
    plain = {"execute: ['AC_get_var', {'name': 'a'}]": {"count": 3, "items": ["a"]}}
    assert displayable_record(plain) == plain


def test_the_builder_tab_does_not_put_the_token_in_its_result_pane(monkeypatch, tmp_path):
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication

    from je_auto_control.gui.script_builder import builder_tab

    app = QApplication.instance() or QApplication([])
    users = str(tmp_path / "users.json")
    tab = builder_tab.ScriptBuilderTab()
    try:
        tab._tree.load_steps([Step("AC_user_add", {"user_id": "eve", "users_path": users})])
        seen = []

        def run(actions, **keywords):
            record = execute_action(actions, **keywords)
            seen.extend(value["token"] for value in record.values())
            return record
        monkeypatch.setattr(builder_tab, "execute_action", run)
        tab._on_run()
        # The run answers on a worker thread now; wait for its result.
        from headless._qt_settle import settle
        assert settle(tab._runs, "task")
        text = tab._result.toPlainText()
        assert len(seen) == 1 and seen[0] not in text
        assert "eve" in text
    finally:
        tab.deleteLater()
        app.processEvents()
