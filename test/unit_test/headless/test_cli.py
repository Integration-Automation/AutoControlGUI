"""Tests for the CLI entry point (argument parsing + dry-run execution)."""
import json
import sys
import threading

import pytest

import je_auto_control as ac
from je_auto_control.cli import _parse_vars, build_parser, main


def test_parse_vars_json_values():
    result = _parse_vars(["count=10", "name=\"alice\"", "active=true"])
    assert result == {"count": 10, "name": "alice", "active": True}


def test_parse_vars_falls_back_to_string():
    result = _parse_vars(["path=C:/Users/Name"])
    assert result == {"path": "C:/Users/Name"}


def test_parse_vars_rejects_missing_equals():
    with pytest.raises(SystemExit):
        _parse_vars(["nope"])


def test_parse_vars_accepts_none():
    assert _parse_vars(None) == {}


def test_build_parser_requires_subcommand():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_run_dry_run_does_not_invoke_actions(tmp_path, capsys):
    script = tmp_path / "s.json"
    script.write_text(
        json.dumps([["AC_click_mouse", {"mouse_keycode": "mouse_left"}]]),
        encoding="utf-8",
    )
    rc = main(["run", str(script), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert any("dry-run" in key for key in payload)


def test_list_jobs_prints_nothing_when_empty(capsys):
    rc = main(["list-jobs"])
    assert rc == 0
    # default_scheduler is shared; we just check that output is tab-separated
    out = capsys.readouterr().out
    for line in out.splitlines():
        assert "\t" in line


def _write(tmp_path, actions, name="s.json"):
    path = tmp_path / name
    path.write_text(json.dumps(actions), encoding="utf-8")
    return str(path)


def test_validate_accepts_valid_file(tmp_path):
    assert main(["validate", _write(tmp_path, [["AC_screen_size"]])]) == 0


def test_lint_alias_accepts_valid_file(tmp_path):
    assert main(["lint", _write(tmp_path, [["AC_screen_size"]])]) == 0


def test_validate_rejects_unknown_command(tmp_path):
    assert main(["validate", _write(tmp_path, [["AC_not_a_real_command"]])]) == 1


def test_validate_missing_file_returns_one(tmp_path):
    assert main(["validate", str(tmp_path / "missing.json")]) == 1


def test_list_commands_text_filtered(capsys):
    assert main(["list-commands", "--filter", "mouse"]) == 0
    out = capsys.readouterr().out
    assert "AC_click_mouse" in out


def test_list_commands_json_is_sorted(capsys):
    assert main(["list-commands", "--json"]) == 0
    names = json.loads(capsys.readouterr().out)
    assert "AC_screen_size" in names
    assert names == sorted(names)


def test_fmt_check_then_reformat(tmp_path, capsys):
    path = _write(tmp_path, [["AC_screen_size"]])
    assert main(["fmt", "--check", path]) == 1   # compact -> drift
    assert main(["fmt", path]) == 0              # reformat in place
    capsys.readouterr()
    assert main(["fmt", "--check", path]) == 0   # now canonical


def test_format_action_json_helper_is_idempotent(tmp_path):
    path = _write(tmp_path, [["AC_screen_size"]])
    assert ac.format_action_json(path, check=True) is True
    assert ac.format_action_json(path) is True
    assert ac.format_action_json(path) is False
    assert ac.format_action_json(path, check=True) is False


def test_record_subcommand_delegates_to_helper(tmp_path, monkeypatch):
    captured = {}

    def fake_record_to_json(output_path, *, stop_event, timeout=None):
        captured["output"] = output_path
        captured["timeout"] = timeout
        return [["AC_type_keyboard", {"keycode": "a"}]]

    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_record.record_to_json",
        fake_record_to_json)
    out = str(tmp_path / "rec.json")
    rc = main(["record", out, "--duration", "0"])
    if sys.platform == "darwin":
        assert rc == 1
    else:
        assert rc == 0
        assert captured["output"] == out
        assert captured["timeout"] == 0.0


def test_record_to_json_helper_writes_file(tmp_path, monkeypatch):
    recorded = [["AC_type_keyboard", {"keycode": "x"}]]
    import je_auto_control.wrapper.auto_control_record as rec_mod
    monkeypatch.setattr(rec_mod, "record", lambda: None)
    monkeypatch.setattr(rec_mod, "stop_record", lambda: recorded)
    out = str(tmp_path / "rec2.json")
    event = threading.Event()
    event.set()  # return immediately without real recording
    actions = ac.record_to_json(out, stop_event=event)
    assert actions == recorded
    assert json.loads(
        (tmp_path / "rec2.json").read_text(encoding="utf-8")) == recorded


def test_version_subcommand(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip()


def test_top_level_import_stays_qt_free():
    """Import the facade in a fresh interpreter so the check isn't polluted
    by GUI tests that may have already imported PySide6 in this session."""
    import subprocess
    script = (
        "import sys, je_auto_control as ac\n"
        "ac.format_action_json; ac.record_to_json  # touch CLI helpers\n"
        "qt = [m for m in sys.modules if 'PySide6' in m]\n"
        "import json; print(json.dumps(qt))\n"
    )
    result = subprocess.run(  # nosec B603  # nosemgrep
        [sys.executable, "-c", script],
        capture_output=True, text=True, check=True, timeout=60,
    )
    assert result.stdout.strip() in ("[]", "")
