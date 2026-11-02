"""``write_secret`` types a password exactly and leaves it nowhere else.

``write`` logs the string it types, records it in the test record and returns
it, so a password typed through it reaches the log and every run record. These
tests pin the three places ``write_secret`` must not leave it (log, record,
return value, including a failure's message) and that every character goes
through Unicode key events, so a capital letter is typed as itself.

Nothing here touches the real desktop: the keyboard backend is a recorder.
"""
import logging

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlKeyboardException
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.test_record.record_test_class import test_record_instance
from je_auto_control.wrapper import auto_control_keyboard as kb

SECRET = "Pa55,wörd😀"


class _UnicodeBackend:
    """A keyboard backend that records the UTF-16 units it is asked to type."""

    def __init__(self, fail_on=None):
        self.units = []
        self._fail_on = fail_on

    def type_unicode_unit(self, unit):
        if unit == self._fail_on:
            raise OSError(f"SendInput refused unit {unit}")
        self.units.append(unit)


class _NoUnicodeBackend:
    """A backend without Unicode typing (what non-Windows backends look like)."""

    def press_key(self, *_args, **_kwargs):
        raise AssertionError("write_secret must not fall back to virtual keys")

    release_key = press_key


def _typed(units):
    return b"".join(unit.to_bytes(2, "little") for unit in units).decode("utf-16-le")


@pytest.fixture
def record_on():
    previous = test_record_instance.init_record
    test_record_instance.set_record_enable(True)
    test_record_instance.clean_record()
    yield test_record_instance
    test_record_instance.clean_record()
    test_record_instance.set_record_enable(previous)


@pytest.fixture
def log_lines():
    lines = []

    class _Collect(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage())

    handler = _Collect(level=logging.DEBUG)
    logger = logging.getLogger("AutoControlGUI")
    previous = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield lines
    logger.removeHandler(handler)
    logger.setLevel(previous)


def test_types_every_character_exactly(monkeypatch):
    backend = _UnicodeBackend()
    monkeypatch.setattr(kb, "keyboard", backend)
    assert kb.write_secret(SECRET) is None
    assert _typed(backend.units) == SECRET


def test_the_secret_reaches_neither_log_nor_record(monkeypatch, record_on, log_lines):
    monkeypatch.setattr(kb, "keyboard", _UnicodeBackend())
    kb.write_secret(SECRET)
    assert log_lines
    assert all("Pa55" not in line for line in log_lines)
    assert record_on.test_record_list[-1]["function_name"] == "write_secret"
    assert "Pa55" not in repr(record_on.test_record_list)


def test_a_failure_names_neither_the_secret_nor_its_characters(monkeypatch, record_on, log_lines):
    monkeypatch.setattr(kb, "keyboard", _UnicodeBackend(fail_on=ord("5")))
    with pytest.raises(AutoControlKeyboardException) as caught:
        kb.write_secret(SECRET)
    message = str(caught.value)
    assert "refused" not in message
    assert "53" not in message
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
    assert all("53" not in line for line in log_lines)
    assert record_on.test_record_list == []


def test_a_backend_without_unicode_typing_refuses_before_typing(monkeypatch):
    monkeypatch.setattr(kb, "keyboard", _NoUnicodeBackend())
    with pytest.raises(AutoControlKeyboardException, match="cannot type Unicode"):
        kb.write_secret(SECRET)


def test_a_non_string_is_refused(monkeypatch):
    monkeypatch.setattr(kb, "keyboard", _UnicodeBackend())
    with pytest.raises(AutoControlKeyboardException):
        kb.write_secret(12345)


def test_registered_as_an_action_command(monkeypatch):
    backend = _UnicodeBackend()
    monkeypatch.setattr(kb, "keyboard", backend)
    assert executor.event_dict["AC_write_secret"] is kb.write_secret
    executor.execute_action([["AC_write_secret", {"secret": "abc"}]])
    assert _typed(backend.units) == "abc"


@pytest.mark.parametrize("argument", [{"secret": "Pa55word"}, ["Pa55word"]])
def test_the_executor_masks_the_argument_in_log_and_record_key(monkeypatch, log_lines, argument):
    monkeypatch.setattr(kb, "keyboard", _UnicodeBackend())
    record = executor.execute_action([["AC_write_secret", argument]])
    assert record
    assert all("Pa55" not in str(key) for key in record)
    assert all("Pa55" not in line for line in log_lines)
