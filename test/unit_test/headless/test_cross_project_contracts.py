"""The contracts other repositories rely on (``architecture.md`` §6).

Nothing on the consumer side tests these, and nothing here did either, so a
rename in this repository broke them silently (workspace item X-7).

**Legacy CLI.** PyBreeze starts ``python -m je_auto_control --execute_str
<json>`` -- and on Windows JSON-encodes that string a *second* time
(``pybreeze/extend/process_executor/python_task_process_manager.py``,
``start_test_process``) -- and ``--execute_file <path>``; TestPioneer's
``parallel_run`` starts ``--execute_file <path>``. The flags are run here as a
real child process from a scratch directory, because the package writes its
log to the current directory. ``execute_action`` swallows per-action errors
and the process exits 0 regardless, so a zero exit proves nothing: every case
checks a file the action list itself writes.

**In-process names.** PyBreeze calls ``je_auto_control.create_project_dir()``
through ``importlib`` and embeds ``je_auto_control.gui.main_widget.
AutoControlGUIWidget``; TestPioneer imports ``execute_action``,
``execute_files`` and ``RecordingThread``; Jeffrey_RPA drives this working
tree through ``JeffreyRPA/_gui_control.py`` and reaches three internal modules
directly. Only the names are pinned -- what they do is covered elsewhere.
"""
import ast
import json
import os
import subprocess  # nosec B404  # reason: the CLI is exercised as a real child process
import sys
from pathlib import Path

import pytest

import je_auto_control

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE = "je_auto_control"


def _run_cli(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """Run ``python -m je_auto_control`` from this checkout inside ``cwd``."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(REPO_ROOT), env.get("PYTHONPATH")]))
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(  # nosec B603  # nosemgrep  # reason: fixed interpreter, test-controlled argv
        [sys.executable, "-m", PACKAGE, *args],
        cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
        timeout=300, check=False,
    )


def _actions(target: Path) -> list:
    """An action list whose only effect is writing ``target``."""
    return [["AC_export_sarif", {"findings": [], "path": str(target)}]]


def _assert_ran(result: subprocess.CompletedProcess, target: Path) -> None:
    assert result.returncode == 0, result.stderr[-2000:]
    assert target.is_file(), (
        "the process exited 0 but the action list did not run:\n"
        + result.stderr[-2000:])


# === Legacy CLI =============================================================

@pytest.mark.parametrize("flag", ["-e", "--execute_file"])
def test_execute_file(tmp_path, flag):
    target = tmp_path / "out.sarif"
    action_file = tmp_path / "actions.json"
    action_file.write_text(json.dumps(_actions(target)), encoding="utf-8")
    _assert_ran(_run_cli(tmp_path, flag, str(action_file)), target)


@pytest.mark.parametrize("flag", ["-d", "--execute_dir"])
def test_execute_dir(tmp_path, flag):
    target = tmp_path / "out.sarif"
    action_dir = tmp_path / "actions"
    action_dir.mkdir()
    (action_dir / "actions.json").write_text(
        json.dumps(_actions(target)), encoding="utf-8")
    _assert_ran(_run_cli(tmp_path, flag, str(action_dir)), target)


@pytest.mark.parametrize("encodings", [1, 2], ids=["posix", "windows"])
def test_execute_str_as_pybreeze_sends_it(tmp_path, encodings):
    """Both shapes on every platform: the decode must not depend on the OS.

    PyBreeze encodes once on POSIX and twice on Windows. ``__main__`` undoes
    the second layer with an ``isinstance`` check rather than a platform
    check, so a Windows-shaped string sent from anywhere still runs.
    """
    target = tmp_path / "out.sarif"
    payload = _actions(target)
    for _ in range(encodings):
        payload = json.dumps(payload)
    _assert_ran(_run_cli(tmp_path, "--execute_str", payload), target)


@pytest.mark.parametrize("flag", ["-c", "--create_project"])
def test_create_project(tmp_path, flag):
    project = tmp_path / "project"
    result = _run_cli(tmp_path, flag, str(project))
    assert result.returncode == 0, result.stderr[-2000:]
    keywords = list((project / "AutoControl" / "keyword").glob("*.json"))
    assert keywords, result.stderr[-2000:]


def test_no_flag_exits_non_zero(tmp_path):
    """A caller that forgot its flag must see a failure, not a silent 0."""
    assert _run_cli(tmp_path).returncode != 0


# === In-process names =======================================================

@pytest.mark.parametrize("name", [
    # PyBreeze: `safe_create_project` and the AutoControl menu.
    "create_project_dir", "record", "stop_record",
    # TestPioneer: the gui-runner and its video recorder.
    "execute_action", "execute_files", "RecordingThread",
    # Jeffrey_RPA: every `ac.<name>` in JeffreyRPA/_gui_control.py.
    "arrange_grid", "click_mouse", "foreground_keyboard_layout",
    "get_clipboard", "get_mouse_position", "get_pixel", "group_lines",
    "hotkey", "match_template_all", "mouse_scroll", "post_click_to_window",
    "post_key_to_window", "press_keyboard_key", "press_mouse",
    "release_keyboard_key", "release_mouse", "restore_window_layout",
    "save_window_layout", "screen_size", "set_clipboard",
    "set_mouse_position", "snap_window", "wait_until_clipboard_changes",
    "wait_until_port", "wait_until_process", "write",
])
def test_facade_name_other_repositories_call(name):
    assert name in je_auto_control.__all__, f"{name} left the facade"
    assert callable(getattr(je_auto_control, name))


@pytest.mark.parametrize("name", [
    "close_window_by_title", "focus_window", "foreground_window",
    "foreground_window_process_id", "list_windows", "move_window_by_title",
    "show_window_by_title", "window_rect",
])
def test_window_module_jeffrey_rpa_reaches_into(name):
    """``from je_auto_control.wrapper import auto_control_window``."""
    from je_auto_control.wrapper import auto_control_window
    assert callable(getattr(auto_control_window, name))


def test_internal_names_jeffrey_rpa_imports():
    from je_auto_control.utils.monitor_layout import (
        enumerate_monitors, logical_virtual_rect,
    )
    from je_auto_control.wrapper.auto_control_keyboard import (
        WRITE_CONTROL_KEYS,
    )
    assert callable(enumerate_monitors) and callable(logical_virtual_rect)
    # Jeffrey_RPA falls back to its own table unless this is a non-empty dict.
    assert isinstance(WRITE_CONTROL_KEYS, dict) and WRITE_CONTROL_KEYS


def test_gui_widget_pybreeze_embeds_is_still_there():
    """Read, not imported: importing it needs PySide6, which CI lacks here."""
    source = (REPO_ROOT / "je_auto_control" / "gui" / "main_widget.py"
              ).read_text(encoding="utf-8")
    classes = {node.name for node in ast.walk(ast.parse(source))
               if isinstance(node, ast.ClassDef)}
    assert "AutoControlGUIWidget" in classes


def test_key_tables_jeffrey_rpa_reads():
    """``platform_wrapper.keyboard_keys_table`` / ``mouse_keys_table``.

    Jeffrey_RPA validates every key name a user types against the keyboard
    table before sending it, and reverse-looks-up recorded virtual keys
    through it, so a name that disappears from it becomes a rejected hotkey
    there. Its own fixture asserts at least 100 entries, and it names these
    keys directly.
    """
    from je_auto_control.wrapper import platform_wrapper

    keyboard = platform_wrapper.keyboard_keys_table
    mouse = platform_wrapper.mouse_keys_table
    assert isinstance(keyboard, dict) and len(keyboard) >= 100
    assert isinstance(mouse, dict) and len(mouse) >= 3
    for name in ("mouse_left", "mouse_right", "mouse_middle"):
        assert name in mouse, name
    for name in ("up", "down", "left", "right", "space", "tab", "shift",
                 "a", "z", "0", "9", "f1", "f12"):
        assert name in keyboard, name


@pytest.mark.skipif(not sys.platform.startswith("win"),
                    reason="Jeffrey_RPA drives Windows; other backends name "
                           "their keys differently and it skips there too")
def test_windows_key_names_jeffrey_rpa_sends():
    """Names Jeffrey_RPA's aliases resolve to, as this backend spells them.

    Its own alias test fails when a target disappears, but only once someone
    runs that suite; this is the side that ships the table.
    """
    from je_auto_control.wrapper import platform_wrapper

    for name in ("return", "escape", "control", "menu", "back", "delete",
                 "home", "end", "insert", "capital", "vk_down"):
        assert name in platform_wrapper.keyboard_keys_table, name
