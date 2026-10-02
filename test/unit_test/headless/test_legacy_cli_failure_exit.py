"""Legacy runners report contained action failures to subprocess callers."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
FAILURE = [["AC_for_each", {"items": 5, "body": [["AC_set_var", {"name": "x", "value": 1}]]}]]
SUCCESS = [["AC_set_var", {"name": "x", "value": 1}]]


def _run(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "-m", "je_auto_control", *args],
        cwd=tmp_path, env=dict(os.environ, PYTHONPATH=str(ROOT)),
        capture_output=True, text=True, timeout=60, check=False,
    )


def test_execute_str_failure_exit_one(tmp_path):
    failed = _run(tmp_path, "--execute_str", json.dumps(FAILURE))
    succeeded = _run(tmp_path, "--execute_str", json.dumps(SUCCESS))
    assert failed.returncode == 1
    assert "1 action(s) failed" in failed.stderr
    assert succeeded.returncode == 0, succeeded.stderr


@pytest.mark.parametrize("flag", ["-e", "-d"])
def test_legacy_file_and_directory_failure_exit_one(tmp_path, flag):
    script = tmp_path / "a.json"
    script.write_text(json.dumps(FAILURE), encoding="utf-8")
    target = tmp_path if flag == "-d" else script
    assert _run(tmp_path, flag, str(target)).returncode == 1
    script.write_text(json.dumps(SUCCESS), encoding="utf-8")
    assert _run(tmp_path, flag, str(target)).returncode == 0


def test_directory_retains_failures_from_earlier_files(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(FAILURE), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(SUCCESS), encoding="utf-8")
    failed = _run(tmp_path, "-d", str(tmp_path))
    assert failed.returncode == 1
    assert "1 action(s) failed" in failed.stderr


def test_multiple_legacy_arguments_accumulate_failures(tmp_path):
    script = tmp_path / "a.json"
    script.write_text(json.dumps(FAILURE), encoding="utf-8")
    failed = _run(tmp_path, "-e", str(script), "--execute_str", json.dumps(FAILURE))
    assert failed.returncode == 1
    assert "2 action(s) failed" in failed.stderr
