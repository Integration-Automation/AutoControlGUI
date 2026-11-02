"""Owned POSIX fixtures preserve raw bytes, redact diagnostics and keep finite guard checks unchanged."""
from itertools import permutations
from subprocess import TimeoutExpired
from unittest.mock import Mock

import pytest

from .android_shell_fixture import AndroidShellFixture
from .test_agent_android_scope import snapshot as snapshot, run_guard as run_guard, WM
from je_auto_control.utils.agent_runtime.android_commands import compile_android_action


@pytest.mark.parametrize("order", list(permutations(range(3))))
def test_focus_guard_accepts_all_field_orders_without_normalizing_values(run_guard, tmp_path, order):
    lines = WM.splitlines(keepends=True)
    (tmp_path / "wm").write_text("".join(lines[index] for index in order), encoding="utf-8", newline="")
    result = run_guard()
    assert result.returncode == 0 and (tmp_path / "actions").read_text().splitlines().count("tap") == 1


@pytest.mark.parametrize("data", [b"", b"line\n\n", b"no-final-newline", b"a\x00b\x00\x00", b"\xff\xfe\n\\  \r\n"])
@pytest.mark.parametrize("fallback", [False, True])
def test_fast_fixture_reader_preserves_exact_bytes_including_nulls_and_newlines(tmp_path, snapshot, data, fallback):
    fixture = AndroidShellFixture(tmp_path, snapshot)
    (tmp_path / "device").write_bytes(data)
    prefix = "unset BASH_VERSION; " if fallback else ""
    result = fixture.run(prefix + "/system/bin/getprop ro.serialno")
    assert result.returncode == 0 and result.stdout == data


def test_fixture_timeout_diagnostic_has_phase_and_duration_but_no_command_or_output(tmp_path, snapshot, monkeypatch):
    fixture = AndroidShellFixture(tmp_path, snapshot)
    secret = "fixture-secret-argument"
    run = Mock(side_effect=TimeoutExpired(["sh", secret], 5, output=b"private-output", stderr=b"private-error"))
    monkeypatch.setattr("subprocess.run", run)
    with pytest.raises(AssertionError) as error:
        fixture.run("/system/bin/input -d 0 text " + secret)
    assert str(error.value) == "Android fixture action shell exceeded its five-second deadline"
    diagnostics = fixture.diagnostics()
    assert diagnostics[-1]["phase"] == "action" and diagnostics[-1]["outcome"] == "timeout"
    assert isinstance(diagnostics[-1]["seconds"], float)
    assert secret not in repr(diagnostics) and "private" not in repr(diagnostics)
    assert run.call_args.kwargs["timeout"] == 5


@pytest.mark.parametrize("field", ["mTopFocusedDisplayId", "mCurrentFocus", "mFocusedApp"])
@pytest.mark.parametrize("post", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_duplicate_focus_fields_including_empty_values_fail_on_the_correct_side_of_input(
        run_guard, tmp_path, field, post, empty):
    line = next(line for line in WM.splitlines() if field + "=" in line)
    duplicate = field + "=" if empty else line
    path = tmp_path / ("after" if post else "wm")
    path.write_text(WM + duplicate + "\n", encoding="utf-8", newline="")
    result = run_guard()
    assert result.returncode == 93
    assert (tmp_path / "actions").exists() is post
    assert (b"post_refused:93" if post else b"refused:93") in result.stdout


def test_raw_labels_cannot_replace_a_missing_native_focus_field(run_guard, tmp_path):
    missing = WM.replace("mTopFocusedDisplayId=0", "display=0")
    (tmp_path / "wm").write_text(missing, encoding="utf-8", newline="")
    assert run_guard().returncode == 93 and not (tmp_path / "actions").exists()


def test_shell_metacharacters_and_globs_in_current_focus_cannot_match_or_execute(tmp_path, snapshot):
    fixture = AndroidShellFixture(tmp_path, snapshot)
    hostile = WM.replace(snapshot.window, "Window{[a]* $(touch injected) 'quoted'}")
    (tmp_path / "wm").write_text(hostile, encoding="utf-8", newline="")
    result = fixture.run(compile_android_action(snapshot, "AC_android_tap", {"x": 1, "y": 2}))
    assert result.returncode == 93 and not (tmp_path / "injected").exists()
    assert not (tmp_path / "actions").exists()
