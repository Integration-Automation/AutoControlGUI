"""CLI, legacy entry point and pytest-plugin defects from the 2026-09-24 audit.

``-d`` listed files in file-system order and followed junctions out of the
directory; the legacy entry point printed nothing on failure; ``run --dry-run
--var`` rejected loop bodies; ``validate`` disagreed with ``run`` on wrapped
and empty files; a failed ``AC_run_suite`` exited 0; ``start-server --port 0``
reported port 0; and the pytest plugin crashed the session when a screenshot
failed and screenshotted skipped tests. Only pure commands run.
"""
import json
import os
import subprocess  # nosec B404  # reason: runs this interpreter only
import sys
import types

import pytest

from je_auto_control.utils.file_process.get_dir_file_list import get_dir_files_as_list

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _cli(*args, cwd):
    env = dict(os.environ, PYTHONPATH=REPO)
    return subprocess.run([sys.executable, *args], capture_output=True, text=True,  # nosec B603  # nosemgrep
                          cwd=cwd, env=env, timeout=120, check=False)


def test_a_directory_is_listed_in_sorted_order(tmp_path):
    for name in ("b.json", "A.json", "_x.json", "c.txt"):
        (tmp_path / name).write_text("[]", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "z.json").write_text("[]", encoding="utf-8")
    names = [os.path.relpath(path, tmp_path) for path in get_dir_files_as_list(str(tmp_path))]
    assert names == ["A.json", "_x.json", "b.json", os.path.join("sub", "z.json")]


def test_a_link_out_of_the_directory_is_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.json").write_text("[]", encoding="utf-8")
    inside = tmp_path / "inside"
    inside.mkdir()
    link = inside / "link"
    try:
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],  # nosec B603 B607  # nosemgrep
                           check=True, capture_output=True)
        else:
            link.symlink_to(outside, target_is_directory=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("cannot create a directory link here")
    assert get_dir_files_as_list(str(inside)) == []


def test_the_legacy_entry_point_says_why_it_failed(tmp_path):
    result = _cli("-m", "je_auto_control", "-e", str(tmp_path / "missing.json"), cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr.startswith("error:")


def test_a_dry_run_with_vars_accepts_loop_bodies(tmp_path):
    script = tmp_path / "loop.json"
    script.write_text(json.dumps([["AC_for_each", {"items": [1, 2], "as": "item",
                                                  "body": [["AC_set_var", {"name": "x", "value": "${item}"}]]}]]),
                      encoding="utf-8")
    result = _cli("-m", "je_auto_control.cli", "run", str(script), "--dry-run", "--var", "z=1", cwd=tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("content, code", [
    ({"auto_control": [["AC_set_var", {"name": "a", "value": 1}]]}, 0),
    ([], 1),
])
def test_validate_agrees_with_run(tmp_path, content, code):
    script = tmp_path / "s.json"
    script.write_text(json.dumps(content), encoding="utf-8")
    assert _cli("-m", "je_auto_control.cli", "validate", str(script), cwd=tmp_path).returncode == code


def test_a_failed_suite_fails_the_run(tmp_path):
    suite = {"name": "s", "cases": [{"name": "c", "actions": [
        ["AC_for_each", {"items": 5, "body": [["AC_set_var", {"name": "v", "value": 1}]]}]]}]}
    script = tmp_path / "suite.json"
    script.write_text(json.dumps([["AC_run_suite", {"spec": suite}]]), encoding="utf-8")
    result = _cli("-m", "je_auto_control.cli", "run", str(script), cwd=tmp_path)
    assert result.returncode == 1


def test_the_plugin_survives_a_failed_screenshot(tmp_path, monkeypatch):
    from je_auto_control.utils.exception.exceptions import AutoControlScreenException
    from je_auto_control.utils.pytest_plugin import plugin
    from je_auto_control.wrapper import auto_control_screen

    def broken(**_kwargs):
        raise AutoControlScreenException("no display")

    monkeypatch.setattr(auto_control_screen, "screenshot", broken)
    sections = []
    item = types.SimpleNamespace(nodeid="t.py::test_x",
                                 add_report_section=lambda *args: sections.append(args))
    assert plugin._capture_failure_screenshot(item, tmp_path) is None
    assert sections and "no display" in sections[0][2]
