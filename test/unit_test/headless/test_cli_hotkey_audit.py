"""Regression tests for the CLI / hotkey / recording defects of the 2026-09-23 audit.

``je_auto_control run`` exited 0 when actions failed; ``failure-bundle`` with a
non-object ``--context`` crashed with a traceback; a recording that could not
start overwrote the output file with ``[]``; a second recording leaked the
first input hook. Hotkeys mapped punctuation to unrelated virtual keys,
accepted combos Windows cannot register and then retried them every tick,
and an error from an injected executor or the run history ended the listener.
"""
import json
import os
import subprocess  # nosec B404  # reason: runs this package's own entry point
import sys
from pathlib import Path

import pytest

from je_auto_control import cli
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.hotkey import hotkey_daemon
from je_auto_control.utils.hotkey.backends.windows_backend import WindowsHotkeyBackend
from je_auto_control.utils.input_macro.recorder_base import InputRecorder
from je_auto_control.wrapper import auto_control_record


REPO_ROOT = Path(__file__).resolve().parents[3]


def _legacy(tmp_path, *args):
    """Run ``python -m je_auto_control`` on this working tree, not an installed copy."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT), env.get("PYTHONPATH")]))
    # argv is sys.executable plus this test's own literals.
    return subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit  # nosec B603
        [sys.executable, "-m", "je_auto_control", *args],
        capture_output=True, timeout=120, check=False, cwd=tmp_path, env=env)


def _script(tmp_path, actions):
    path = tmp_path / "flow.json"
    path.write_text(json.dumps(actions), encoding="utf-8")
    return str(path)


# --- CLI ----------------------------------------------------------------------

def test_run_exits_non_zero_when_an_action_fails(tmp_path, capsys):
    rc = cli.main(["run", _script(tmp_path, [["AC_sleep", {"seconds": -1}]])])
    assert rc == 1
    assert "1 action(s) failed" in capsys.readouterr().err


def test_run_exits_zero_when_every_action_succeeds(tmp_path):
    assert cli.main(["run", _script(tmp_path, [["AC_set_var", {"name": "x", "value": 1}]])]) == 0


def test_a_non_object_bundle_context_is_an_error_message(tmp_path, capsys):
    rc = cli.main(["failure-bundle", str(tmp_path / "b.zip"), "--context", "[1]",
                   "--no-screenshot", "--no-diagnostics"])
    assert rc == 1
    assert "JSON object" in capsys.readouterr().err


def test_a_recording_that_cannot_start_leaves_the_file_alone(tmp_path, monkeypatch):
    target = tmp_path / "precious.json"
    target.write_text('[["AC_keep"]]', encoding="utf-8")
    monkeypatch.setattr(auto_control_record, "record", lambda: False)
    with pytest.raises(AutoControlException, match="not written"):
        auto_control_record.record_to_json(str(target), stop_event=None, timeout=0)
    assert target.read_text(encoding="utf-8") == '[["AC_keep"]]'


def test_the_legacy_entry_point_reports_a_missing_directory(tmp_path):
    completed = _legacy(tmp_path, "-d", str(tmp_path / "no_such_dir"))
    assert completed.returncode == 1
    assert b"Traceback" not in completed.stderr


def test_the_legacy_entry_point_reports_a_missing_file_without_a_traceback(tmp_path):
    completed = _legacy(tmp_path, "-e", str(tmp_path / "missing.json"))
    assert completed.returncode == 1
    assert b"Traceback" not in completed.stderr


# --- recording ----------------------------------------------------------------

class _Hook:
    live = 0

    def start(self):
        _Hook.live += 1

    def stop(self):
        _Hook.live -= 1
        return []


def test_a_second_recording_stops_the_first_hook():
    recorder = InputRecorder()
    recorder.new_hook = _Hook
    _Hook.live = 0
    recorder.record()
    recorder.record()
    recorder.stop_record()
    assert _Hook.live == 0


# --- hotkeys ------------------------------------------------------------------

@pytest.mark.parametrize("key, vk", [(".", 0xBE), ("-", 0xBD), (",", 0xBC), ("/", 0xBF),
                                     ("[", 0xDB), ("`", 0xC0), (";", 0xBA), ("a", 0x41), ("7", 0x37)])
def test_keys_map_to_their_own_virtual_key(key, vk):
    assert hotkey_daemon.parse_combo(f"ctrl+{key}")[1] == vk


def test_an_unmappable_key_is_refused():
    with pytest.raises(ValueError):
        hotkey_daemon.parse_combo("ctrl+é")


@pytest.mark.skipif(sys.platform != "win32", reason="bind() checks the Windows key table on Windows")
def test_bind_refuses_a_combo_windows_cannot_register():
    with pytest.raises(ValueError):
        hotkey_daemon.HotkeyDaemon().bind("ctrl+foo", "s.json")


class _User32:
    def __init__(self):
        self.attempts = 0

    def RegisterHotKey(self, *_args):  # noqa: N802 - Win32 name
        self.attempts += 1
        return 0

    def UnregisterHotKey(self, *_args):  # noqa: N802 - Win32 name
        return 1


def test_a_combo_that_fails_to_register_is_not_retried_every_tick():
    backend, user32 = WindowsHotkeyBackend(), _User32()
    binding = hotkey_daemon.HotkeyBinding(binding_id="b1", combo="ctrl+k", script_path="s.json")
    for _ in range(20):
        backend._sync(user32, [binding])
    assert user32.attempts == 1
    binding.combo = "ctrl+j"
    backend._sync(user32, [binding])
    assert user32.attempts == 2, "a changed combo is tried again"


def test_an_injected_executor_error_does_not_escape_the_listener(tmp_path, monkeypatch):
    def broken(_actions):
        raise KeyError("x")

    daemon = hotkey_daemon.HotkeyDaemon(executor=broken)
    binding = daemon.bind("ctrl+k", _script(tmp_path, [["AC_noop"]]))
    daemon._fire_binding(binding.binding_id)  # must not raise
    assert binding.fired == 1


def test_a_history_failure_does_not_escape_the_listener(tmp_path, monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise AutoControlException("database is locked")

    monkeypatch.setattr(hotkey_daemon.default_history_store, "start_run", unavailable)
    daemon = hotkey_daemon.HotkeyDaemon(executor=lambda actions: None)
    binding = daemon.bind("ctrl+k", _script(tmp_path, [["AC_noop"]]))
    daemon._fire_binding(binding.binding_id)
    assert binding.fired == 1
