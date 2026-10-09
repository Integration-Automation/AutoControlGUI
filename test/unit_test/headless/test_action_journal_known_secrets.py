"""Values the run resolved from a secret are masked by exact match.

Pattern redaction cannot know that ``tangerine-47-osprey`` is a password. The
recorder can: the run read it from the vault, typed it or interpolated it.
A fake vault and fake commands; nothing is typed.
"""
import pytest

from je_auto_control.utils.action_journal import recorder
from je_auto_control.utils.action_journal.events import MASK
from je_auto_control.utils.action_journal.store import read_events
from je_auto_control.utils.executor.action_executor import Executor

# No credential syntax and low entropy: the pattern redaction lets these through.
PLAIN = "tangerine osprey 47"
QUOTED = 'it\'s a "quoted" one\\two'


class _FakeVault:
    def __init__(self, items):
        self._items = items

    def get(self, name):
        return self._items.get(name)


@pytest.fixture(autouse=True)
def _journal_off():
    recorder.stop_action_journal()
    yield
    recorder.stop_action_journal()


@pytest.fixture
def fake_executor(monkeypatch):
    import je_auto_control.utils.secrets as secrets_module
    monkeypatch.setattr(secrets_module, "default_secret_manager",
                        _FakeVault({"plain": PLAIN, "quoted": QUOTED}))
    executor = Executor()

    def fake_fail(**kwargs):
        raise RuntimeError(f"server said: bad login with {kwargs.get('text')} for ada")

    executor.event_dict.update({
        "AC_fake_fail": fake_fail, "AC_fake_step": lambda **kwargs: len(kwargs)})
    return executor


def _file_text(path):
    return path.read_text(encoding="utf-8")


def test_the_pattern_alone_lets_the_value_through():
    from je_auto_control.utils.config_redaction.config_redaction import redact_secret_text
    assert PLAIN in redact_secret_text(f"bad login with {PLAIN} for ada")


def test_a_secret_reference_resolved_by_the_run_is_masked_in_the_error(
        tmp_path, fake_executor):
    journal = tmp_path / "journal.jsonl"
    recorder.start_action_journal(journal)
    fake_executor.execute_action([["AC_fake_fail", {"text": "${secrets.plain}"}]])
    recorder.stop_action_journal()
    event = read_events(journal)[0]
    assert event.params == {"text": "${secrets.plain}"}
    assert event.error == f"RuntimeError('server said: bad login with {MASK} for ada')"
    assert PLAIN not in _file_text(journal)


def test_the_escaped_form_an_error_repr_holds_is_masked_too(tmp_path, fake_executor):
    journal = tmp_path / "journal.jsonl"
    recorder.start_action_journal(journal)
    fake_executor.execute_action([["AC_fake_fail", {"text": "${secrets.quoted}"}]])
    recorder.stop_action_journal()
    text = _file_text(journal)
    assert "quoted" not in text.replace("secrets.quoted", "")
    assert "one" not in text
    assert MASK in read_events(journal)[0].error


def test_a_value_noted_earlier_is_masked_in_later_arguments_and_artifacts(
        tmp_path, fake_executor):
    journal = tmp_path / "journal.jsonl"
    recorder.start_action_journal(journal)
    assert recorder.note_secret_value(PLAIN) is True
    fake_executor.execute_action([
        ["AC_fake_step", {"text": f"say {PLAIN} now", "items": [PLAIN, "public"]}]])
    recorder.note_artifact("report", path=f"/tmp/{PLAIN}.html")
    recorder.stop_action_journal()
    event = read_events(journal)[0]
    assert event.params == {"text": f"say {MASK} now", "items": [MASK, "public"]}
    assert set(event.unreplayable) == {"params.text", "params.items[0]"}
    assert [dict(item) for item in event.artifacts] == [
        {"kind": "report", "path": f"/tmp/{MASK}.html"}]
    assert PLAIN not in _file_text(journal)


def test_a_secret_cut_by_the_length_limit_leaves_no_prefix(tmp_path, fake_executor):
    journal = tmp_path / "journal.jsonl"
    padding = "x" * (recorder._MAX_ERROR_CHARS - 40)
    fake_executor.event_dict["AC_fake_long"] = lambda: (_ for _ in ()).throw(
        RuntimeError(padding + PLAIN))
    recorder.start_action_journal(journal)
    recorder.note_secret_value(PLAIN)
    fake_executor.execute_action([["AC_fake_long"]])
    recorder.stop_action_journal()
    assert "tangerine" not in _file_text(journal)


def test_write_secret_input_and_vault_reads_are_noted(tmp_path, monkeypatch):
    import je_auto_control.wrapper.auto_control_keyboard as keyboard_module
    from je_auto_control.utils.secret_ref.secret_ref import RefResolver
    noted = []
    monkeypatch.setattr(recorder, "note_secret_value",
                        lambda value: noted.append(value) or True)
    # Refuse before any key event: the note has to happen first.
    monkeypatch.setattr(keyboard_module, "keyboard", object())
    with pytest.raises(Exception):
        keyboard_module.write_secret(PLAIN)
    resolver = RefResolver(secret_resolver=lambda name: f"value-of-{name}")
    assert resolver.resolve("secret://db") == "value-of-db"
    assert noted == [PLAIN, "value-of-db"]


def test_the_real_vault_notes_what_it_reads_and_stores(tmp_path, monkeypatch):
    pytest.importorskip("cryptography", exc_type=ImportError)
    from je_auto_control.utils.secrets.secret_store import SecretManager
    noted = []
    monkeypatch.setattr(recorder, "note_secret_value",
                        lambda value: noted.append(value) or True)
    vault = SecretManager(tmp_path / "vault.json")
    vault.initialize("passphrase for the test vault")
    vault.set("api", PLAIN)
    assert vault.get("api") == PLAIN
    assert vault.get("missing") is None
    assert noted == [PLAIN, PLAIN]


def test_short_values_and_no_journal_are_ignored(tmp_path):
    assert recorder.note_secret_value(PLAIN) is False  # no journal started
    recorder.start_action_journal(tmp_path / "journal.jsonl")
    assert recorder.note_secret_value("abc") is False
    assert recorder.note_secret_value(None) is False
    assert recorder.note_secret_value("abcd") is True


def test_values_are_dropped_when_the_journal_stops(tmp_path):
    recorder.start_action_journal(tmp_path / "journal.jsonl")
    recorder.note_secret_value(PLAIN)
    stopped = recorder.stop_action_journal()
    assert PLAIN not in repr(stopped)
    assert recorder._LAST is not None
    assert recorder._LAST.secret_values() == ()
