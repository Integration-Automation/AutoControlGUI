"""The Script Builder reveals a run's freshly issued token once, and only on screen.

``AC_user_add`` / ``AC_user_rotate_token`` answer with a bearer token, and the
builder masks it in its result pane -- so whoever ran the step there never saw
it. The values of the last run are now held in memory until the "one-time
values" button hands them to a dialog; the tab forgets them at that moment,
when the next run starts and when it is disposed, and the dialog forgets them
when it closes.

The first tests are headless (what the run produced, how each value is named).
The rest build the tab offscreen; the dialog is built and inspected but never
shown or executed, and the clipboard is replaced by a list.
"""
import json
import logging
from pathlib import Path

import pytest

from je_auto_control.gui.script_builder.step_model import (
    OneTimeValue, Step, displayable_record, nested_sensitive_commands, one_time_values,
    save_action_file, steps_to_actions,
)
from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.rbac import UserStore

_KEYS = ("sb_one_time_show", "sb_one_time_title", "sb_one_time_notice", "sb_one_time_step",
         "sb_one_time_copy", "sb_one_time_available", "sb_one_time_nested")
_ADD_KEY = "execute: ['AC_user_add', {'user_id': 'x'}]"


def _user_steps(users: str) -> list:
    return [
        Step("AC_user_add", {"user_id": "ann", "role": "operator", "users_path": users}),
        Step("AC_user_list", {"users_path": users}),
        Step("AC_user_rotate_token", {"user_id": "ann", "users_path": users}),
    ]


# --- headless: what a run produced -------------------------------------------


def test_the_headless_run_still_returns_the_token_and_names_each_by_its_step(tmp_path):
    users = str(tmp_path / "users.json")
    record = execute_action(steps_to_actions(_user_steps(users)))
    values = one_time_values(record)
    assert [(value.step, value.command, value.subject, value.name) for value in values] == [
        (1, "AC_user_add", "ann", "token"), (3, "AC_user_rotate_token", "ann", "token")]
    assert values[0].value == list(record.values())[0]["token"], "the record is not changed"
    assert UserStore(users).authenticate(values[1].value).user_id == "ann"


def test_a_value_is_not_in_the_text_form_of_its_holder():
    value = OneTimeValue(1, "AC_user_add", "ann", "token", "tok-in-memory-only")
    assert "tok-in-memory-only" not in repr(value) + str(value) + f"{[value]}"


def test_a_failed_or_empty_marked_command_has_nothing_to_reveal():
    assert one_time_values({_ADD_KEY: "UserAuthError('user exists')"}) == []
    assert one_time_values({_ADD_KEY: None}) == []
    assert one_time_values({_ADD_KEY: {"user_id": "x", "token": ""}}) == []
    assert one_time_values("not a record") == []


def test_a_marked_result_without_fields_is_revealed_whole():
    values = one_time_values({_ADD_KEY: ["opaque", "values"]})
    assert [(value.step, value.name, value.value) for value in values] == [
        (1, "", json.dumps(["opaque", "values"]))]


def test_a_marked_result_in_a_nested_record_keeps_the_top_level_step_number():
    record = {"execute: ['AC_get_var', {'name': 'a'}]": 1,
              "execute: ['AC_try', {}]": {"body": [{_ADD_KEY: {"user_id": "x", "token": "tok-nested"}}]}}
    values = one_time_values(record)
    assert [(value.step, value.subject, value.value) for value in values] == [(2, "x", "tok-nested")]


def test_everything_revealed_is_exactly_what_the_display_masks(tmp_path):
    users = str(tmp_path / "users.json")
    record = execute_action(steps_to_actions(_user_steps(users)))
    shown = json.dumps(displayable_record(record), default=str)
    raw = json.dumps(record, default=str)
    for value in one_time_values(record):
        assert value.value in raw and value.value not in shown


def test_marked_commands_inside_a_block_are_named_and_top_level_ones_are_not():
    actions = [
        ["AC_user_add", {"user_id": "top"}],
        ["AC_loop", {"times": 2, "body": [
            ["AC_user_rotate_token", {"user_id": "a"}],
            ["AC_try", {"body": [["AC_user_add", {"user_id": "b"}]], "catch": []}]]}],
        ["AC_user_list"],
    ]
    assert nested_sensitive_commands(actions) == ["AC_user_add", "AC_user_rotate_token"]
    assert nested_sensitive_commands(actions[:1] + actions[2:]) == []
    assert nested_sensitive_commands({"not": "a list"}) == []


def test_a_block_really_records_no_nested_token(tmp_path):
    """Why the note exists: the value issued in a body is in no record to reveal."""
    users = str(tmp_path / "users.json")
    record = execute_action([["AC_loop", {"times": 1, "body": [
        ["AC_user_add", {"user_id": "bob", "users_path": users}]]}]])
    assert UserStore(users).get("bob") is not None and one_time_values(record) == []


def test_a_signed_jwt_is_masked_revealed_once_and_kept_out_of_the_log(caplog):
    """The schema flag was missing: the builder printed the credential it had just minted."""
    autocontrol_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=autocontrol_logger.name):
            record = execute_action([["AC_jwt_encode", {"claims": {"sub": "ann"}, "key": "k" * 40}]])
    finally:
        autocontrol_logger.removeHandler(caplog.handler)
    token = list(record.values())[0]["token"]
    assert token.count(".") == 2, "the script still gets the signed token"
    assert token not in json.dumps(displayable_record(record))
    assert [(value.step, value.name, value.value) for value in one_time_values(record)] == [
        (1, "token", token)]
    logged = "\n".join(entry.getMessage() for entry in caplog.records)
    assert "AC_jwt_encode" in logged and token not in logged


def test_a_result_is_logged_with_its_secret_named_fields_masked_at_any_depth(caplog):
    """The result log printed a lease token; the record a script receives is untouched."""
    autocontrol_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=autocontrol_logger.name):
            record = execute_action([["AC_lease_secret", {"name": "db", "ttl": 5}], ["AC_lease_active"]])
    finally:
        autocontrol_logger.removeHandler(caplog.handler)
    issued, active = record.values()
    assert issued["token"] in [lease["token"] for lease in active["leases"]]
    logged = "\n".join(entry.getMessage() for entry in caplog.records)
    assert "AC_lease_active" in logged and "'name': 'db'" in logged
    assert issued["token"] not in logged
    execute_action([["AC_revoke_lease", {"token": issued["token"]}]])


def test_the_extraction_is_free_of_qt():
    import je_auto_control.gui.script_builder.step_model as step_model
    assert "PySide6" not in Path(step_model.__file__).read_text(encoding="utf-8")


def test_the_strings_exist_in_every_catalogue_with_the_same_placeholders():
    import re

    from je_auto_control.gui.language_wrapper.english import english_word_dict
    from je_auto_control.gui.language_wrapper.japanese import japanese_word_dict
    from je_auto_control.gui.language_wrapper.simplified_chinese import simplified_chinese_word_dict
    from je_auto_control.gui.language_wrapper.traditional_chinese import traditional_chinese_word_dict

    def placeholders(text: str) -> list:
        return sorted(re.findall(r"\{(\w+)\}", text))

    for catalogue in (japanese_word_dict, simplified_chinese_word_dict, traditional_chinese_word_dict):
        for key in _KEYS:
            assert catalogue[key].strip()
            assert placeholders(catalogue[key]) == placeholders(english_word_dict[key]), key


# --- the tab, offscreen ------------------------------------------------------


@pytest.fixture()
def builder(monkeypatch):
    """A Script Builder tab, its module, and the list standing in for the clipboard."""
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication

    from je_auto_control.gui.script_builder import builder_tab, one_time_dialog

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    copied: list = []
    monkeypatch.setattr(one_time_dialog, "_copy_to_clipboard", copied.append)

    def refuse(*_args, **_kwargs):
        raise AssertionError("the reveal dialog must never run a nested event loop")
    monkeypatch.setattr(one_time_dialog.OneTimeValueDialog, "exec", refuse)
    tab = builder_tab.ScriptBuilderTab()
    try:
        yield tab, builder_tab, copied
    finally:
        tab.dispose()
        tab.deleteLater()
        app.processEvents()


def _run(tab, steps) -> None:
    from headless._qt_settle import settle

    tab._tree.load_steps(steps)
    tab._on_run()
    assert settle(tab._runs, "task")


def _translated(key: str, **fields) -> str:
    from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
    return language_wrapper.translate(key, key).format(**fields)


def test_the_result_pane_masks_and_says_values_are_available(builder, tmp_path):
    tab, _module, _copied = builder
    assert not tab._reveal_btn.isEnabled(), "nothing to reveal before a run"
    _run(tab, _user_steps(str(tmp_path / "users.json")))
    text = tab._result.toPlainText()
    tokens = [value.value for value in tab._one_time]
    assert len(tokens) == 2 and all(len(token) > 20 for token in tokens)
    assert not any(token in text for token in tokens)
    assert '"token": "***"' in text and "ann" in text, "the masked record is still shown"
    assert _translated("sb_one_time_available", count=2) in text
    assert tab._reveal_btn.isEnabled()
    assert tab._reveal_dialog is None, "nothing opens by itself"


def test_the_dialog_shows_each_value_labelled_by_its_step_and_only_once(builder, tmp_path):
    tab, _module, copied = builder
    users = str(tmp_path / "users.json")
    _run(tab, _user_steps(users))
    tokens = [value.value for value in tab._one_time]
    dialog = tab._take_one_time_dialog()
    assert dialog.shown_values() == tokens
    assert dialog.labels() == [
        " · ".join((_translated("sb_one_time_step", step=1), "User: Add", "ann", "token")),
        " · ".join((_translated("sb_one_time_step", step=3), "User: Rotate Token", "ann", "token")),
    ]
    assert not dialog.isVisible() and not dialog.isModal(), "built, not shown"
    assert tab._one_time == [] and not tab._reveal_btn.isEnabled()
    assert tab._take_one_time_dialog() is None, "a second reveal has nothing left"
    assert dialog.copy_value(1) and copied == [tokens[1]]
    assert UserStore(users).authenticate(copied[0]).user_id == "ann", "what is copied is the live token"
    assert not dialog.copy_value(5)


def test_closing_the_dialog_forgets_every_value(builder, tmp_path):
    tab, _module, copied = builder
    _run(tab, _user_steps(str(tmp_path / "users.json")))
    dialog = tab._take_one_time_dialog()
    assert tab._reveal_dialog is dialog
    dialog.reject()  # what the Close button and the window's close box do
    assert dialog.shown_values() == ["", ""] and dialog.labels() == []
    assert not dialog.copy_value(0) and copied == []
    assert tab._reveal_dialog is None and tab._one_time == []
    assert tab._take_one_time_dialog() is None


def test_the_button_opens_the_dialog_without_a_nested_event_loop(builder, tmp_path, monkeypatch):
    tab, _module, _copied = builder
    from je_auto_control.gui.script_builder.one_time_dialog import OneTimeValueDialog

    opened: list = []
    monkeypatch.setattr(OneTimeValueDialog, "open", lambda dialog: opened.append(dialog))
    tab._reveal_btn.click()
    assert opened == [], "a click with nothing pending opens nothing"
    _run(tab, _user_steps(str(tmp_path / "users.json")))
    tab._reveal_btn.click()
    assert opened == [tab._reveal_dialog] and len(opened[0].shown_values()) == 2
    opened[0].reject()


def test_the_next_run_drops_values_nobody_revealed(builder, tmp_path):
    tab, _module, _copied = builder
    users = str(tmp_path / "users.json")
    _run(tab, _user_steps(users))
    assert len(tab._one_time) == 2
    _run(tab, [Step("AC_user_list", {"users_path": users})])
    assert tab._one_time == [] and not tab._reveal_btn.isEnabled()
    assert _translated("sb_one_time_available", count=2) not in tab._result.toPlainText()


def test_the_next_run_empties_a_dialog_still_holding_values(builder, tmp_path):
    tab, _module, copied = builder
    users = str(tmp_path / "users.json")
    _run(tab, _user_steps(users))
    dialog = tab._take_one_time_dialog()
    _run(tab, [Step("AC_user_list", {"users_path": users})])
    assert dialog.shown_values() == ["", ""] and not dialog.copy_value(0) and copied == []
    assert tab._reveal_dialog is None


def test_disposing_the_tab_forgets_pending_values_and_the_dialog(builder, tmp_path):
    tab, _module, _copied = builder
    users = str(tmp_path / "users.json")
    _run(tab, _user_steps(users))
    tab.dispose()
    assert tab._one_time == [] and not tab._reveal_btn.isEnabled()
    _run(tab, _user_steps(users)[2:])
    dialog = tab._take_one_time_dialog()
    tab.dispose()
    assert dialog.shown_values() == [""]


def test_a_failed_step_offers_nothing(builder, tmp_path):
    tab, _module, _copied = builder
    users = str(tmp_path / "users.json")
    UserStore(users).add_user(user_id="root", display_name="root", role="admin")
    _run(tab, [Step("AC_user_rotate_token", {"user_id": "nobody", "users_path": users})])
    assert tab._one_time == [] and not tab._reveal_btn.isEnabled()
    assert "nobody" in tab._result.toPlainText()


def test_a_token_issued_inside_a_block_is_reported_as_unavailable(builder, tmp_path):
    tab, _module, _copied = builder
    users = str(tmp_path / "users.json")
    _run(tab, [Step("AC_loop", {"times": 1}, bodies={"body": [
        Step("AC_user_add", {"user_id": "bob", "users_path": users})]})])
    assert UserStore(users).get("bob") is not None
    assert _translated("sb_one_time_nested", commands="AC_user_add") in tab._result.toPlainText()
    assert tab._one_time == [] and not tab._reveal_btn.isEnabled()


# --- the value reaches nothing that is kept ----------------------------------


class _Writes:
    """Everything handed to a store that persists, as text."""

    def __init__(self) -> None:
        self.seen: list = []

    def recorder(self, name: str, result=True):
        def record(_self, *args, **kwargs):
            self.seen.append(f"{name} {args!r} {kwargs!r} {json.dumps([args, kwargs], default=str)}")
            return result
        return record


def test_the_token_reaches_no_log_record_journal_history_script_or_setting(
        builder, tmp_path, monkeypatch, caplog):
    from je_auto_control.gui.window_settings import WindowSettings
    from je_auto_control.utils.action_journal.recorder import (
        start_action_journal, stop_action_journal,
    )
    from je_auto_control.utils.run_history.history_store import HistoryStore
    from je_auto_control.utils.test_record.record_test_class import test_record_instance

    tab, _module, copied = builder
    users = str(tmp_path / "users.json")
    journal = tmp_path / "journal.jsonl"
    saved = tmp_path / "saved.json"
    writes = _Writes()
    for name in ("start_run", "finish_run", "attach_artifact", "link_journal"):
        monkeypatch.setattr(HistoryStore, name, writes.recorder(f"history.{name}", result=1))
    for name in ("save", "save_form"):
        monkeypatch.setattr(WindowSettings, name, writes.recorder(f"settings.{name}"))
    monkeypatch.setattr(test_record_instance, "init_record", True)
    monkeypatch.setattr(test_record_instance, "test_record_list", [])
    autocontrol_logger.addHandler(caplog.handler)
    start_action_journal(journal)
    try:
        with caplog.at_level(logging.DEBUG, logger=autocontrol_logger.name):
            _run(tab, _user_steps(users))
            pane_before = tab._result.toPlainText()
            dialog = tab._take_one_time_dialog()
            tokens = dialog.shown_values()
            dialog.copy_value(0)
            dialog.copy_value(1)
            dialog.reject()
            save_action_file(str(saved), tab._tree.root_steps(), tab._file_extras)
    finally:
        stop_action_journal()
        autocontrol_logger.removeHandler(caplog.handler)
    assert len(tokens) == 2 and copied == tokens, "the values were really revealed and copied"
    assert UserStore(users).authenticate(tokens[1]).user_id == "ann"

    outputs = {
        "result pane before the reveal": pane_before,
        "result pane after the reveal": tab._result.toPlainText(),
        "log": "\n".join(entry.getMessage() for entry in caplog.records),
        "test record": repr(test_record_instance.test_record_list),
        "run history and GUI settings writes": "\n".join(writes.seen),
        "the tab's steps": json.dumps(steps_to_actions(tab._tree.root_steps())),
    }
    for path in sorted(tmp_path.rglob("*")):
        if path.is_file():
            outputs[f"file {path.name}"] = path.read_bytes().decode("utf-8", errors="replace")
    assert "AC_user_add" in outputs["log"], "the run was logged"
    assert "AC_user_add" in outputs["file journal.jsonl"], "the run was journalled"
    assert "AC_user_add" in outputs["file saved.json"], "the script was saved"
    assert "file users.json" in outputs, "the store (hashes only) is searched too"
    for name, text in outputs.items():
        for token in tokens:
            assert token not in text, f"the token reached: {name}"


def test_the_reveal_code_names_no_store_that_persists():
    """The dialog and the tab hold the values; neither module can write them anywhere."""
    # Read as text: importing the modules needs a Qt that some CI images lack.
    package = Path(__file__).resolve().parents[3] / "je_auto_control" / "gui" / "script_builder"
    dialog_source = (package / "one_time_dialog.py").read_text(encoding="utf-8")
    for word in ("autocontrol_logger", "QSettings", "window_settings", "run_history",
                 "test_record", "action_journal", "open(", "write"):
        assert word not in dialog_source.replace("dialog.open()", "").replace("``open()``", ""), word
    tab_source = (package / "builder_tab.py").read_text(encoding="utf-8")
    for word in ("autocontrol_logger", "QSettings", "window_settings", "run_history", "test_record"):
        assert word not in tab_source, word
