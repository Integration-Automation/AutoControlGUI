"""Public journal entry points preserve run, storage and CLI contracts."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import je_auto_control as ac
from je_auto_control.cli import main
from je_auto_control.utils import action_journal
from je_auto_control.utils.action_journal.capture import current_journal
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.run_history import JournalLink


def test_facade_capture_and_filtered_read_keep_original_results(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setitem(executor.event_dict, "AC_public_journal_probe", lambda value: seen.append(value) or value)
    path = tmp_path / "public.jsonl"
    actions = [["AC_public_journal_probe", {"value": "${message}"}]]
    result = ac.execute_action_with_journal(actions, path, variables={"message": "hello"}, run_id="public")
    assert seen == ["hello"] and result["failed_actions"] == 0
    assert result["record"] and result["run_id"] == "public"
    assert ac.read_events(path, run_id="other") == []
    assert [event.status for event in ac.read_events(path, run_id="public")] == ["incomplete", "ok"]
    assert actions[0][1]["value"] == "${message}" and current_journal() is None
    for name in action_journal.__all__:
        assert name in ac.__all__ and getattr(ac, name) is getattr(action_journal, name)
    assert ac.JournalLink is JournalLink and "JournalLink" in ac.__all__


def _script(tmp_path, actions):
    path = tmp_path / "actions.json"
    path.write_text(json.dumps(actions), encoding="utf-8")
    return str(path)


def test_cli_capture_keeps_stdout_and_variable_execution(tmp_path, monkeypatch, capsys):
    seen = []
    monkeypatch.setitem(executor.event_dict, "AC_public_journal_probe", lambda value: seen.append(value) or value)
    script = _script(tmp_path, [["AC_public_journal_probe", {"value": "${message}"}]])
    path = tmp_path / "cli.jsonl"
    assert main(["run", script, "--var", "message=hello", "--journal", str(path),
                 "--journal-run-id", "cli"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "journal_path" not in payload and seen == ["hello"]
    events = action_journal.read_events(path)
    assert [event.status for event in events] == ["incomplete", "ok"]
    assert all(event.run_id == "cli" for event in events)
    assert current_journal() is None


def test_cli_dry_run_capture_avoids_dispatch(tmp_path, monkeypatch, capsys):
    def fail():
        pytest.fail("dry-run dispatched an action")
    monkeypatch.setitem(executor.event_dict, "AC_public_journal_probe", fail)
    path = tmp_path / "dry.jsonl"
    script = _script(tmp_path, [["AC_public_journal_probe"]])
    assert main(["run", script, "--dry-run", "--journal", str(path)]) == 0
    assert any("dry-run" in key for key in json.loads(capsys.readouterr().out))
    assert [event.status for event in action_journal.read_events(path)] == ["incomplete", "dry_run"]


def test_cli_failed_action_retains_exit_code_and_journal_status(tmp_path, monkeypatch, capsys):
    def fail():
        raise ValueError("controlled action failure")
    monkeypatch.setitem(executor.event_dict, "AC_public_journal_probe", fail)
    script = _script(tmp_path, [["AC_public_journal_probe"]])
    path = tmp_path / "failed.jsonl"
    assert main(["run", script, "--journal", str(path)]) == 1
    assert "1 action(s) failed" in capsys.readouterr().err
    assert [event.status for event in action_journal.read_events(path)] == ["incomplete", "error"]


def test_cli_foreign_destination_is_preserved_before_effects(tmp_path, monkeypatch, capsys):
    seen = []
    monkeypatch.setitem(executor.event_dict, "AC_public_journal_probe", lambda: seen.append(True))
    script = _script(tmp_path, [["AC_public_journal_probe"]])
    path = tmp_path / "foreign.txt"
    path.write_bytes(b"leave this file intact\n")
    assert main(["run", script, "--journal", str(path)]) == 1
    assert seen == [] and path.read_bytes() == b"leave this file intact\n"
    assert "error:" in capsys.readouterr().err and current_journal() is None


def test_cli_run_id_requires_capture(tmp_path, capsys):
    script = _script(tmp_path, [["AC_screen_size"]])
    assert main(["run", script, "--journal-run-id", "unused"]) == 1
    assert "requires --journal" in capsys.readouterr().err


def test_cli_journal_filters_bounds_and_does_not_rewrite(tmp_path, capsys):
    path = tmp_path / "read.jsonl"
    journal = action_journal.ActionJournal(path)
    for sequence in range(4):
        journal.append(action_journal.ActionEvent(run_id="one" if sequence < 3 else "two",
                       step_id=str(sequence), command="AC_write", parameters={"password": "fake-private-text"},
                       started_at=1))
    # An external producer may bypass the writer's masking. The CLI applies
    # the same policy at presentation without modifying the original file.
    external = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for item in external:
        item["parameters"]["password"] = "fake-private-text"
    path.write_text("".join(json.dumps(item) + "\n" for item in external), encoding="utf-8")
    before = path.read_bytes()
    assert main(["journal", str(path), "--run-id", "one", "--limit", "2"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["sequence"] for item in payload] == [1, 2]
    assert all(item["run_id"] == "one" and item["status"] == "incomplete" for item in payload)
    assert "fake-private-text" not in json.dumps(payload)
    assert path.read_bytes() == before


def test_cli_capture_preserves_cancellation_and_restores_context(tmp_path, monkeypatch):
    signal = asyncio.CancelledError("controlled cancellation")
    def cancel():
        raise signal
    monkeypatch.setitem(executor.event_dict, "AC_public_journal_probe", cancel)
    script = _script(tmp_path, [["AC_public_journal_probe"]])
    path = tmp_path / "cancelled.jsonl"
    with pytest.raises(asyncio.CancelledError) as caught:
        main(["run", script, "--journal", str(path)])
    assert caught.value is signal and current_journal() is None
    assert [event.status for event in action_journal.read_events(path)] == ["incomplete", "cancelled"]


@pytest.mark.parametrize("limit", ["0", "-1", "10001", "invalid"])
def test_cli_journal_rejects_invalid_output_limits(tmp_path, limit):
    with pytest.raises(SystemExit) as error:
        main(["journal", str(tmp_path / "absent.jsonl"), "--limit", limit])
    assert error.value.code == 2


def test_cli_journal_corruption_never_prints_raw_input(tmp_path, capsys):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"password":"fake-private-value"}\n', encoding="utf-8")
    assert main(["journal", str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "fake-private-value" not in captured.err


def test_cli_journal_missing_path_is_empty_without_creation(tmp_path, capsys):
    path = tmp_path / "absent.jsonl"
    assert main(["journal", str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == [] and not path.exists()


@pytest.mark.parametrize("command", ["run", "journal"])
def test_cli_journal_paths_use_allowed_roots(tmp_path, monkeypatch, capsys, command):
    from je_auto_control.utils.path_guard import path_guard
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setattr(path_guard, "default_allowed_roots", lambda: [allowed])
    path = tmp_path / "outside.jsonl"
    args = ["journal", str(path)] if command == "journal" else [
        "run", _script(tmp_path, [["AC_screen_size"]]), "--journal", str(path)]
    assert main(args) == 1
    assert "error:" in capsys.readouterr().err and not path.exists()


def test_public_and_cli_journals_work_without_qt_or_sqlite(tmp_path):
    probe = '''
import sys
from pathlib import Path
class Blocker:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"PySide6", "sqlite3", "_sqlite3"}:
            raise ModuleNotFoundError("optional dependency blocked", name=fullname)
sys.meta_path.insert(0, Blocker())
import je_auto_control as ac
from je_auto_control.cli import main
path = Path(sys.argv[1])
ac.execute_action_with_journal([["AC_screen_size"]], path, dry_run=True)
if main(["journal", str(path)]) != 0:
    raise SystemExit("journal read failed")
if any(name.split(".")[0] in {"PySide6", "sqlite3", "_sqlite3"} for name in sys.modules):
    raise SystemExit("optional dependencies were imported")
if (Path.home() / ".je_auto_control").exists():
    raise SystemExit("an implicit state directory was created")
'''
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               PYTHONPATH=str(Path(__file__).resolve().parents[3]))
    env.pop("HOMEDRIVE", None)
    env.pop("HOMEPATH", None)
    result = subprocess.run(  # nosec B603  # nosemgrep  # reason: fixed probe with a temporary path as data; no shell
        [sys.executable, "-c", probe, str(tmp_path / "headless.jsonl")],
        env=env, capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert [event["status"] for event in json.loads(result.stdout)] == ["incomplete", "dry_run"]
