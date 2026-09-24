"""Hand-edited inputs saved with a UTF-8 BOM (Notepad) read the same as without.

``read_action_json`` -- and so ``je_auto_control validate`` -- already
accepted a BOM, but every path that runs a file (``run``, ``-e``, the
scheduler, triggers, hotkeys, MCP) refused it, as did the action linter. A
``.env`` file lost its first key without a word.
"""
import codecs
import json

from je_auto_control.utils.action_lint.linter import _main as lint_main
from je_auto_control.utils.dotenv.dotenv import dotenv_values
from je_auto_control.utils.json.json_file import (
    read_action_json, read_executable_action_json,
)

ACTIONS = [["AC_get_mouse_table"]]


def _with_bom(path, text):
    path.write_bytes(codecs.BOM_UTF8 + text.encode("utf-8"))
    return str(path)


def test_a_file_that_validates_also_runs(tmp_path):
    path = _with_bom(tmp_path / "script.json", json.dumps(ACTIONS))
    assert read_action_json(path) == ACTIONS
    assert read_executable_action_json(path) == ACTIONS


def test_the_linter_reads_a_bom_file(tmp_path, capsys):
    path = _with_bom(tmp_path / "script.json", json.dumps(ACTIONS))
    lint_main([path])
    assert "BOM" not in capsys.readouterr().err


def test_the_linter_reports_a_file_that_is_not_utf8(tmp_path, capsys):
    path = tmp_path / "script.json"
    path.write_bytes(b"\xff\xfe[")
    assert lint_main([str(path)]) == 1
    assert str(path) in capsys.readouterr().err


def test_a_dotenv_file_keeps_its_first_key(tmp_path):
    path = _with_bom(tmp_path / ".env", "API_URL=https://example.test\nMODE=ci\n")
    assert dotenv_values(path) == {"API_URL": "https://example.test", "MODE": "ci"}
