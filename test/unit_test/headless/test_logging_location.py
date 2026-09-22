"""Where the package log goes, and that opening it can never break the import.

The handler used to open the relative path ``AutoControlGUI.log``, so every
process importing the package -- every pytest run on a machine where it is
installed, through the ``pytest11`` plugin -- left a log in its cwd. Now the
file is ``$JE_AUTOCONTROL_LOG_FILE`` or ``~/.je_auto_control/logs/``, shared by
every process on the account: opened for append, rotated only at open, and a
failure to open it degrades to no file instead of a failed import.
"""
import logging
import os
import subprocess  # nosec B404  # reason: runs the test interpreter on a fixed argv
import sys
from pathlib import Path

import pytest

from je_auto_control.utils.logging import logging_instance as li

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_line(handler, message):
    record = logging.LogRecord("t", logging.INFO, __file__, 1, message, None, None)
    handler.emit(record)
    handler.flush()


def test_the_environment_variable_names_the_file(monkeypatch, tmp_path):
    target = tmp_path / "elsewhere" / "run.log"
    monkeypatch.setenv(li.LOG_FILE_ENV, str(target))
    assert li.default_log_file() == target


def test_without_the_variable_the_file_is_under_the_home_directory(monkeypatch):
    monkeypatch.delenv(li.LOG_FILE_ENV, raising=False)
    assert li.default_log_file() == (
        Path.home() / ".je_auto_control" / "logs" / "AutoControlGUI.log")


def test_a_blank_variable_means_the_default(monkeypatch):
    monkeypatch.setenv(li.LOG_FILE_ENV, "   ")
    assert li.default_log_file().name == "AutoControlGUI.log"
    assert li.default_log_file().is_absolute()


def test_the_handler_creates_the_directory(tmp_path):
    target = tmp_path / "a" / "b" / "c.log"
    handler = li.AutoControlGUILoggingHandler(filename=str(target))
    try:
        _write_line(handler, "hello")
    finally:
        handler.close()
    assert "hello" in target.read_text(encoding="utf-8")


def test_a_second_process_appends_instead_of_truncating(tmp_path):
    """The file is shared; opening it must not wipe another process's lines."""
    target = tmp_path / "shared.log"
    for message in ("first", "second"):
        handler = li.AutoControlGUILoggingHandler(filename=str(target))
        try:
            _write_line(handler, message)
        finally:
            handler.close()
    text = target.read_text(encoding="utf-8")
    assert "first" in text and "second" in text


def test_each_line_carries_the_process_id(tmp_path):
    target = tmp_path / "pid.log"
    handler = li.AutoControlGUILoggingHandler(filename=str(target))
    try:
        _write_line(handler, "who wrote this")
    finally:
        handler.close()
    assert f"| {os.getpid()} |" in target.read_text(encoding="utf-8")


def test_a_large_file_is_rotated_when_opened(monkeypatch, tmp_path):
    monkeypatch.setattr(li, "ROTATE_AT_BYTES", 10)
    target = tmp_path / "big.log"
    target.write_text("x" * 50, encoding="utf-8")
    handler = li.AutoControlGUILoggingHandler(filename=str(target))
    try:
        _write_line(handler, "fresh")
    finally:
        handler.close()
    assert (tmp_path / "big.log.1").read_text(encoding="utf-8") == "x" * 50
    assert "x" * 50 not in target.read_text(encoding="utf-8")


def test_a_small_file_is_left_alone(monkeypatch, tmp_path):
    monkeypatch.setattr(li, "ROTATE_AT_BYTES", 1000)
    target = tmp_path / "small.log"
    target.write_text("kept\n", encoding="utf-8")
    li.AutoControlGUILoggingHandler(filename=str(target)).close()
    assert not (tmp_path / "small.log.1").exists()
    assert target.read_text(encoding="utf-8").startswith("kept")


def test_a_rotation_refused_by_the_os_still_opens_the_file(monkeypatch, tmp_path):
    """Windows refuses the rename while another process holds the file."""
    monkeypatch.setattr(li, "ROTATE_AT_BYTES", 10)

    def _refuse(*_args):
        raise PermissionError("in use")

    monkeypatch.setattr(li.os, "replace", _refuse)
    target = tmp_path / "busy.log"
    target.write_text("x" * 50, encoding="utf-8")
    handler = li.AutoControlGUILoggingHandler(filename=str(target))
    try:
        _write_line(handler, "appended")
    finally:
        handler.close()
    assert "appended" in target.read_text(encoding="utf-8")


def test_an_unopenable_file_degrades_to_devnull_with_one_warning(tmp_path):
    """A path through a regular file cannot be opened; logging must go on."""
    blocker = tmp_path / "not_a_directory"
    blocker.write_text("", encoding="utf-8")
    with pytest.warns(RuntimeWarning, match="unavailable"):
        handler = li.AutoControlGUILoggingHandler(
            filename=str(blocker / "x.log"))
    try:
        _write_line(handler, "goes nowhere")
    finally:
        handler.close()


def test_a_delayed_handler_creates_nothing_until_the_first_record(tmp_path):
    target = tmp_path / "later" / "d.log"
    handler = li.AutoControlGUILoggingHandler(filename=str(target), delay=True)
    try:
        assert not target.parent.exists()
        _write_line(handler, "now")
    finally:
        handler.close()
    assert "now" in target.read_text(encoding="utf-8")


def _run_in_fresh_home(tmp_path, code):
    """Run ``code`` in a new interpreter; return its (cwd, home)."""
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    env = {key: value for key, value in os.environ.items()
           if key != li.LOG_FILE_ENV}
    env.update(HOME=str(home), USERPROFILE=str(home),
               PYTHONPATH=str(_REPO_ROOT))
    env.pop("HOMEDRIVE", None)
    env.pop("HOMEPATH", None)
    subprocess.run(  # nosec B603  # reason: fixed argv, the test interpreter
        [sys.executable, "-c", code],
        cwd=str(work), env=env, check=True, timeout=110)
    return work, home


def test_importing_the_package_writes_no_log_anywhere(tmp_path):
    """The regression itself: the old handler created the file in the cwd."""
    work, home = _run_in_fresh_home(tmp_path, "import je_auto_control")
    assert list(work.iterdir()) == []
    assert list(home.iterdir()) == []


def test_the_first_record_lands_in_the_home_file(tmp_path):
    work, home = _run_in_fresh_home(
        tmp_path,
        "from je_auto_control.utils.logging.logging_instance import "
        "autocontrol_logger as log; log.warning('first record')")
    assert list(work.iterdir()) == []
    log_file = home / ".je_auto_control" / "logs" / "AutoControlGUI.log"
    assert "first record" in log_file.read_text(encoding="utf-8")
