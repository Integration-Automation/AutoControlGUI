"""The Script Builder reveals a run's freshly issued token once, and only on screen.

``AC_user_add`` / ``AC_user_rotate_token`` answer with a bearer token, and the
builder masks it in its result pane -- so whoever ran the step there never saw
it. The values of the last run are held in memory until the "one-time values"
button hands them to a dialog; the tab forgets them at that moment, when the
next run starts and when it is disposed, and the dialog forgets them when it
closes.

The values are gathered from the executor's result hook, so a token issued in
the body of a block (``AC_loop``, ``AC_try``...) is offered too, labelled by
its path; at most ``MAX_ONE_TIME_VALUES`` are kept for one run.

The first tests are headless (what the run produced, how each value is named).
The rest build the tab offscreen; the dialog is built and inspected but never
shown or executed, and the clipboard is a fake.
"""
import json
import logging
from pathlib import Path

import pytest

from je_auto_control.gui.script_builder.step_model import (
    MAX_ONE_TIME_VALUES, OneTimeCollector, OneTimeValue, Step, displayable_record,
    save_action_file, steps_to_actions,
)
from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.executor.result_hook import StepPosition
from je_auto_control.utils.executor.run_control import ExecutionStopped
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.rbac import UserStore

_KEYS = ("sb_one_time_show", "sb_one_time_title", "sb_one_time_notice", "sb_one_time_step",
         "sb_one_time_copy", "sb_one_time_available", "sb_one_time_inside", "sb_one_time_shown",
         "sb_one_time_limit", "sb_one_time_close_clear")
_TOP = (StepPosition(1, 1, "AC_user_add"),)


def _user_steps(users: str) -> list:
    return [
        Step("AC_user_add", {"user_id": "ann", "role": "operator", "users_path": users}),
        Step("AC_user_list", {"users_path": users}),
        Step("AC_user_rotate_token", {"user_id": "ann", "users_path": users}),
    ]


def _loop_step(users: str, times: int = 2) -> Step:
    """A loop whose body lists the users, then issues a token inside an ``AC_try``."""
    return Step("AC_loop", {"times": times}, bodies={"body": [
        Step("AC_user_list", {"users_path": users}),
        Step("AC_try", bodies={"body": [
            Step("AC_user_rotate_token", {"user_id": "ann", "users_path": users})], "catch": []}),
    ]})


def _collected(actions: list, limit: int = MAX_ONE_TIME_VALUES):
    """Run ``actions`` as the builder does: the record, the values kept, whether some were left out."""
    collector = OneTimeCollector(limit)
    record = execute_action(actions, result_callback=collector.note)
    values, truncated = collector.take()
    return record, values, truncated


# --- headless: what a run produced -------------------------------------------


def test_the_headless_run_still_returns_the_token_and_names_each_by_its_step(tmp_path):
    users = str(tmp_path / "users.json")
    record, values, truncated = _collected(steps_to_actions(_user_steps(users)))
    assert [(value.step, value.command, value.subject, value.name) for value in values] == [
        (1, "AC_user_add", "ann", "token"), (3, "AC_user_rotate_token", "ann", "token")]
    assert values[0].value == list(record.values())[0]["token"], "the record is not changed"
    assert UserStore(users).authenticate(values[1].value).user_id == "ann"
    assert not truncated


def test_a_value_is_not_in_the_text_form_of_its_holder():
    value = OneTimeValue(_TOP, "AC_user_add", "ann", "token", "tok-in-memory-only")
    assert "tok-in-memory-only" not in repr(value) + str(value) + f"{[value]}"
    assert value.step == 1


def test_a_failed_or_empty_command_has_nothing_to_reveal(tmp_path):
    users = str(tmp_path / "users.json")
    UserStore(users).add_user(user_id="root", display_name="root", role="admin")
    record, values, _truncated = _collected(
        [["AC_user_rotate_token", {"user_id": "nobody", "users_path": users}]])
    assert "nobody" in list(record.values())[0] and values == []
    collector = OneTimeCollector()
    collector.note("AC_user_add", {"user_id": "x"}, None, _TOP)
    collector.note("AC_user_add", {"user_id": "x"}, {"user_id": "x", "token": ""}, _TOP)
    collector.note("AC_user_add", {"user_id": "x"}, {"user_id": "x", "token": None}, _TOP)
    assert collector.take() == ([], False)


def test_a_marked_result_without_fields_is_hidden_and_revealed_whole():
    key = "execute: ['AC_user_add', {'user_id': 'x'}]"
    assert "opaque" not in json.dumps(displayable_record({key: ["opaque", "values"]}))
    collector = OneTimeCollector()
    collector.note("AC_user_add", {"user_id": "x"}, ["opaque", "values"], _TOP)
    values, _truncated = collector.take()
    assert [(value.step, value.name, value.value) for value in values] == [
        (1, "", json.dumps(["opaque", "values"]))]


def test_a_token_issued_inside_a_block_is_collected_with_its_path(tmp_path):
    """The gap: a block records only its summary, so the value was in no record to reveal."""
    users = str(tmp_path / "users.json")
    actions = steps_to_actions([_user_steps(users)[0], _loop_step(users, times=3)])
    record, values, _truncated = _collected(actions)
    nested = values[1:]
    assert [value.path for value in nested] == [
        (StepPosition(1, 2, "AC_loop"), StepPosition(run, 2, "AC_try"),
         StepPosition(1, 1, "AC_user_rotate_token")) for run in (1, 2, 3)]
    assert {(value.step, value.command, value.subject, value.name) for value in nested} == {
        (2, "AC_user_rotate_token", "ann", "token")}
    assert len({value.value for value in values}) == 4
    assert UserStore(users).authenticate(nested[-1].value).user_id == "ann", "the last one is the live token"
    raw = json.dumps(record, default=str)
    assert not any(value.value in raw for value in nested), "the record still holds only the summary"


def test_a_block_that_returns_its_body_record_does_not_offer_a_value_twice(tmp_path):
    users = str(tmp_path / "users.json")
    record, values, _truncated = _collected([["AC_execute_action", {"action_list": [
        ["AC_user_add", {"user_id": "bob", "users_path": users}]]}]])
    assert [(value.command, len(value.path), value.subject) for value in values] == [
        ("AC_user_add", 2, "bob")]
    shown = json.dumps(displayable_record(record), default=str)
    assert values[0].value in json.dumps(record, default=str) and values[0].value not in shown


def test_a_value_only_a_parallel_branch_produced_is_taken_from_the_block_result():
    """A branch runs on its own thread, which the hook does not follow; its record is in the result."""
    record, values, _truncated = _collected(
        [["AC_parallel", {"branches": [[["AC_lease_secret", {"name": "one-time-par", "ttl": 5}]]]}]])
    try:
        assert [(value.command, value.name) for value in values] == [
            ("AC_parallel", "results[0].AC_lease_secret.token")]
        assert values[0].value not in json.dumps(displayable_record(record), default=str)
    finally:
        execute_action([["AC_revoke_lease", {"token": values[0].value}]])


def test_the_number_of_values_kept_for_one_run_is_bounded(tmp_path):
    users = str(tmp_path / "users.json")
    actions = steps_to_actions([_user_steps(users)[0], _loop_step(users, times=6)])
    _record, values, truncated = _collected(actions, limit=4)
    assert len(values) == 4 and truncated
    assert [value.step for value in values] == [1, 2, 2, 2], "the first ones are the ones kept"
    _record, values, truncated = _collected(
        [["AC_user_rotate_token", {"user_id": "ann", "users_path": users}]], limit=1)
    assert len(values) == 1 and not truncated, "exactly at the limit nothing was left out"
    assert MAX_ONE_TIME_VALUES == 200 and OneTimeCollector().limit == 200


def test_everything_revealed_is_exactly_what_the_display_masks(tmp_path):
    users = str(tmp_path / "users.json")
    record, values, _truncated = _collected(steps_to_actions(_user_steps(users)))
    shown = json.dumps(displayable_record(record), default=str)
    raw = json.dumps(record, default=str)
    assert shown.count('"***"') == len(values) == 2
    for value in values:
        assert value.value in raw and value.value not in shown


def test_a_signed_jwt_is_masked_revealed_once_and_kept_out_of_the_log(caplog):
    """The schema flag was missing: the builder printed the credential it had just minted."""
    autocontrol_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=autocontrol_logger.name):
            record, values, _truncated = _collected(
                [["AC_jwt_encode", {"claims": {"sub": "ann"}, "key": "k" * 40}]])
    finally:
        autocontrol_logger.removeHandler(caplog.handler)
    token = list(record.values())[0]["token"]
    assert token.count(".") == 2, "the script still gets the signed token"
    assert token not in json.dumps(displayable_record(record))
    assert [(value.step, value.name, value.value) for value in values] == [(1, "token", token)]
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

    catalogues = (english_word_dict, japanese_word_dict, simplified_chinese_word_dict,
                  traditional_chinese_word_dict)
    for catalogue in catalogues:
        assert "sb_one_time_nested" not in catalogue, "the 'not available in a block' line is gone"
        for key in _KEYS:
            assert catalogue[key].strip()
            assert placeholders(catalogue[key]) == placeholders(english_word_dict[key]), key


# --- the tab, offscreen ------------------------------------------------------


class _FakeClipboard:
    """Stands in for the system clipboard: what it holds, and every value copied onto it."""

    def __init__(self) -> None:
        self.text = "somebody else's note"
        self.copied: list = []
        self.cleared = 0

    def copy(self, text: str) -> None:
        self.copied.append(text)
        self.text = text

    def clear(self) -> None:
        self.cleared += 1
        self.text = ""


@pytest.fixture()
def builder(monkeypatch):
    """A Script Builder tab, its module, and the fake standing in for the clipboard."""
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication

    from je_auto_control.gui.script_builder import builder_tab, one_time_dialog

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    clipboard = _FakeClipboard()
    monkeypatch.setattr(one_time_dialog, "_copy_to_clipboard", clipboard.copy)
    monkeypatch.setattr(one_time_dialog, "_clipboard_text", lambda: clipboard.text)
    monkeypatch.setattr(one_time_dialog, "_clear_clipboard", clipboard.clear)

    def refuse(*_args, **_kwargs):
        raise AssertionError("the reveal dialog must never run a nested event loop")
    monkeypatch.setattr(one_time_dialog.OneTimeValueDialog, "exec", refuse)
    tab = builder_tab.ScriptBuilderTab()
    try:
        yield tab, builder_tab, clipboard
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


def _label(command: str) -> str:
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    spec = COMMAND_SPECS.get(command)
    return spec.label if spec is not None else command  # a command without a form shows its name


def test_the_result_pane_masks_and_says_values_are_available(builder, tmp_path):
    tab, _module, _clipboard = builder
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
    tab, _module, clipboard = builder
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
    assert dialog.copy_value(1) and clipboard.copied == [tokens[1]]
    assert UserStore(users).authenticate(clipboard.copied[0]).user_id == "ann", \
        "what is copied is the live token"
    assert not dialog.copy_value(5)


def test_a_token_issued_inside_a_block_is_offered_and_labelled_by_its_path(builder, tmp_path):
    tab, _module, _clipboard = builder
    users = str(tmp_path / "users.json")
    _run(tab, [_user_steps(users)[0], _loop_step(users, times=2)])
    text = tab._result.toPlainText()
    assert _translated("sb_one_time_available", count=3) in text
    assert "block" not in text.lower(), "nothing is reported as unavailable any more"
    dialog = tab._take_one_time_dialog()
    tokens = dialog.shown_values()
    assert len(set(tokens)) == 3 and not any(token in text for token in tokens)

    def nested(run: int) -> str:
        path = " › ".join((
            _translated("sb_one_time_step", step=2),
            _translated("sb_one_time_inside", block=_label("AC_loop"), run=run, step=2),
            _translated("sb_one_time_inside", block=_label("AC_try"), run=1, step=1)))
        return " · ".join((path, "User: Rotate Token", "ann", "token"))
    assert dialog.labels()[1:] == [nested(1), nested(2)]
    assert "Step 2 › " + _label("AC_loop") + " run 2, step 2 › " in dialog.labels()[2]
    assert UserStore(users).authenticate(tokens[2]).user_id == "ann"
    dialog.reject()


def test_the_pane_says_when_a_run_issued_more_values_than_are_kept(builder, tmp_path, monkeypatch):
    import functools

    tab, module, _clipboard = builder
    monkeypatch.setattr(module, "OneTimeCollector", functools.partial(OneTimeCollector, 2))
    users = str(tmp_path / "users.json")
    _run(tab, [_user_steps(users)[0], _loop_step(users, times=5)])
    text = tab._result.toPlainText()
    assert len(tab._one_time) == 2
    assert _translated("sb_one_time_available", count=2) in text
    assert _translated("sb_one_time_limit", limit=2) in text
    _run(tab, _user_steps(users)[2:])
    assert _translated("sb_one_time_limit", limit=2) not in tab._result.toPlainText()


def test_the_pane_says_the_values_were_shown_once_the_dialog_was_opened(builder, tmp_path):
    """It kept saying values were available after they had been handed over and dropped."""
    tab, _module, _clipboard = builder
    _run(tab, _user_steps(str(tmp_path / "users.json")))
    available = _translated("sb_one_time_available", count=2)
    assert available in tab._result.toPlainText()
    dialog = tab._take_one_time_dialog()
    text = tab._result.toPlainText()
    assert available not in text and _translated("sb_one_time_shown") in text
    assert '"token": "***"' in text, "the masked record stays"
    dialog.reject()
    assert _translated("sb_one_time_shown") in tab._result.toPlainText()


def test_marking_values_shown_leaves_another_message_in_the_pane_alone(builder, tmp_path):
    tab, _module, _clipboard = builder
    _run(tab, _user_steps(str(tmp_path / "users.json")))
    tab._result.setPlainText("Saved: somewhere.json")
    tab._take_one_time_dialog().reject()
    assert tab._result.toPlainText() == "Saved: somewhere.json"


def test_closing_the_dialog_forgets_every_value(builder, tmp_path):
    tab, _module, clipboard = builder
    _run(tab, _user_steps(str(tmp_path / "users.json")))
    dialog = tab._take_one_time_dialog()
    assert tab._reveal_dialog is dialog
    dialog.reject()  # what the Close button and the window's close box do
    assert dialog.shown_values() == ["", ""] and dialog.labels() == []
    assert not dialog.copy_value(0) and clipboard.copied == []
    assert tab._reveal_dialog is None and tab._one_time == []
    assert tab._take_one_time_dialog() is None
    assert clipboard.cleared == 0 and clipboard.text == "somebody else's note"


def test_clearing_is_offered_only_after_a_copy_and_clears_a_value_still_on_the_clipboard(
        builder, tmp_path):
    tab, _module, clipboard = builder
    _run(tab, _user_steps(str(tmp_path / "users.json")))
    dialog = tab._take_one_time_dialog()
    tokens = dialog.shown_values()
    assert not dialog.can_clear_clipboard() and not dialog._clear_btn.isEnabled()
    assert not dialog.clear_clipboard() and clipboard.cleared == 0, "nothing was copied from here"
    dialog.copy_value(0)
    dialog.copy_value(1)
    assert dialog.can_clear_clipboard() and clipboard.text == tokens[1]
    dialog._clear_btn.click()  # "Close and clear clipboard"
    assert clipboard.cleared == 1 and clipboard.text == ""
    assert dialog.shown_values() == ["", ""] and tab._reveal_dialog is None, "it also closed"
    assert not dialog.can_clear_clipboard()


def test_clearing_leaves_content_somebody_else_put_on_the_clipboard(builder, tmp_path):
    tab, _module, clipboard = builder
    _run(tab, _user_steps(str(tmp_path / "users.json")))
    dialog = tab._take_one_time_dialog()
    dialog.copy_value(0)
    clipboard.text = "a paragraph copied in another window"
    dialog.close_and_clear()
    assert clipboard.cleared == 0 and clipboard.text == "a paragraph copied in another window"
    assert dialog.shown_values() == ["", ""], "the dialog still closed and forgot"


def test_an_earlier_copy_from_the_dialog_still_on_the_clipboard_is_cleared(builder, tmp_path):
    tab, _module, clipboard = builder
    _run(tab, _user_steps(str(tmp_path / "users.json")))
    dialog = tab._take_one_time_dialog()
    first = dialog.shown_values()[0]
    dialog.copy_value(1)
    dialog.copy_value(0)
    assert clipboard.text == first and dialog.clear_clipboard() and clipboard.text == ""
    assert not dialog.clear_clipboard(), "a second clear has nothing of this dialog's to remove"
    dialog.reject()


def test_a_plain_close_after_a_copy_leaves_the_clipboard_for_pasting(builder, tmp_path):
    tab, _module, clipboard = builder
    _run(tab, _user_steps(str(tmp_path / "users.json")))
    dialog = tab._take_one_time_dialog()
    token = dialog.shown_values()[0]
    dialog.copy_value(0)
    dialog.reject()
    assert clipboard.cleared == 0 and clipboard.text == token
    assert not dialog.clear_clipboard(), "once closed the dialog no longer knows the value"


def test_the_button_opens_the_dialog_without_a_nested_event_loop(builder, tmp_path, monkeypatch):
    tab, _module, _clipboard = builder
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
    tab, _module, _clipboard = builder
    users = str(tmp_path / "users.json")
    _run(tab, _user_steps(users))
    assert len(tab._one_time) == 2
    _run(tab, [Step("AC_user_list", {"users_path": users})])
    assert tab._one_time == [] and not tab._reveal_btn.isEnabled()
    assert _translated("sb_one_time_available", count=2) not in tab._result.toPlainText()


def test_the_next_run_empties_a_dialog_still_holding_values(builder, tmp_path):
    tab, _module, clipboard = builder
    users = str(tmp_path / "users.json")
    _run(tab, _user_steps(users))
    dialog = tab._take_one_time_dialog()
    _run(tab, [Step("AC_user_list", {"users_path": users})])
    assert dialog.shown_values() == ["", ""] and not dialog.copy_value(0) and clipboard.copied == []
    assert tab._reveal_dialog is None


def test_disposing_the_tab_forgets_pending_values_and_the_dialog(builder, tmp_path):
    tab, _module, _clipboard = builder
    users = str(tmp_path / "users.json")
    _run(tab, _user_steps(users))
    tab.dispose()
    assert tab._one_time == [] and not tab._reveal_btn.isEnabled()
    _run(tab, _user_steps(users)[2:])
    dialog = tab._take_one_time_dialog()
    tab.dispose()
    assert dialog.shown_values() == [""]


def test_a_failed_step_offers_nothing(builder, tmp_path):
    tab, _module, _clipboard = builder
    users = str(tmp_path / "users.json")
    UserStore(users).add_user(user_id="root", display_name="root", role="admin")
    _run(tab, [Step("AC_user_rotate_token", {"user_id": "nobody", "users_path": users})])
    assert tab._one_time == [] and not tab._reveal_btn.isEnabled()
    assert "nobody" in tab._result.toPlainText()


def test_a_run_that_was_stopped_or_failed_still_offers_what_it_had_issued(builder, monkeypatch):
    tab, module, _clipboard = builder
    warned: list = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *args: warned.append(args[-1]))
    for error in (ExecutionStopped("stopped"), AutoControlActionException("the run broke")):
        tab._collector = OneTimeCollector()
        tab._collector.note("AC_user_add", {"user_id": "ann"}, {"user_id": "ann", "token": "tok-early"}, _TOP)
        tab._show_run_error(error)
        text = tab._result.toPlainText()
        assert _translated("sb_one_time_available", count=1) in text and "tok-early" not in text
        assert [value.value for value in tab._one_time] == ["tok-early"] and tab._reveal_btn.isEnabled()
        tab._forget_one_time()
    assert warned == ["the run broke"]


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


@pytest.mark.parametrize("nested", [False, True], ids=["top-level", "inside a block"])
def test_the_token_reaches_no_log_record_journal_history_script_or_setting(
        builder, tmp_path, monkeypatch, caplog, nested):
    from je_auto_control.gui.window_settings import WindowSettings
    from je_auto_control.utils.action_journal.recorder import (
        start_action_journal, stop_action_journal,
    )
    from je_auto_control.utils.run_history.history_store import HistoryStore
    from je_auto_control.utils.test_record.record_test_class import test_record_instance

    tab, _module, clipboard = builder
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
    steps = _user_steps(users) + ([_loop_step(users, times=2)] if nested else [])
    autocontrol_logger.addHandler(caplog.handler)
    start_action_journal(journal)
    try:
        with caplog.at_level(logging.DEBUG, logger=autocontrol_logger.name):
            _run(tab, steps)
            pane_before = tab._result.toPlainText()
            dialog = tab._take_one_time_dialog()
            tokens = dialog.shown_values()
            for index in range(len(tokens)):
                dialog.copy_value(index)
            dialog.close_and_clear()
            save_action_file(str(saved), tab._tree.root_steps(), tab._file_extras)
    finally:
        stop_action_journal()
        autocontrol_logger.removeHandler(caplog.handler)
    assert len(tokens) == (4 if nested else 2), "the nested tokens were collected too"
    assert clipboard.copied == tokens, "the values were really revealed and copied"
    assert clipboard.text == "", "and the last one was taken off the clipboard again"
    assert UserStore(users).authenticate(tokens[-1]).user_id == "ann"

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
    if nested:
        assert outputs["file journal.jsonl"].count("AC_user_rotate_token") >= 3, \
            "the nested steps were journalled"
    for name, text in outputs.items():
        for token in tokens:
            assert token not in text, f"the token reached: {name}"


def test_the_reveal_code_names_no_store_that_persists():
    """The dialog and the tab hold the values; neither module can write them anywhere."""
    from je_auto_control.gui.script_builder import builder_tab, one_time_dialog

    dialog_source = Path(one_time_dialog.__file__).read_text(encoding="utf-8")
    for word in ("autocontrol_logger", "QSettings", "window_settings", "run_history",
                 "test_record", "action_journal", "open(", "write"):
        assert word not in dialog_source.replace("dialog.open()", "").replace("``open()``", ""), word
    tab_source = Path(builder_tab.__file__).read_text(encoding="utf-8")
    for word in ("autocontrol_logger", "QSettings", "window_settings", "run_history", "test_record"):
        assert word not in tab_source, word
