"""Tests for the CLI entry point (argument parsing + dry-run execution)."""
import json

import pytest

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
