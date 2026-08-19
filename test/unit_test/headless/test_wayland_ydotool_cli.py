"""The ydotool 0.1.x guard: what it classifies, refuses and lets through.

The bug it exists for is measured in ``docker/ydotool_verify.py`` against a
real uinput device — 0.1.x answers this backend's argv with exit code 0 and
no events, so ``check=True`` sees success while nothing happened. These tests
cover the classification and the two backends' use of it without needing
ydotool installed, which is what makes them CI-gating on every platform.
"""
import subprocess
from unittest import mock

import pytest

from je_auto_control.linux_wayland import _ydotool_cli
from je_auto_control.utils.exception.exceptions import AutoControlException


#: The real no-argument banners, copied from ydotool 0.1.8 (Debian bookworm)
#: and 1.0.4 (Debian unstable / Arch). If a future release changes these the
#: probe answers "unknown" and stops refusing anything, which is the safe
#: direction — but docker/ydotool_verify.py fails loudly when it happens.
LEGACY_BANNER = b"""Usage: ydotool <cmd> <args>
Available commands:
  type
  recorder
  mousemove
  key
  click
"""

MODERN_BANNER = b"""Usage: ydotool <cmd> <args>
Available commands:
  click
  mousemove
  type
  key
  debug
  bakers
Use environment variable YDOTOOL_SOCKET to specify daemon socket.
"""


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    """The probe caches per path for the process; tests must not share it."""
    _ydotool_cli.reset_cache()
    yield
    _ydotool_cli.reset_cache()


def _fake_run(stdout=b"", stderr=b"", returncode=0):
    completed = subprocess.CompletedProcess(  # nosemgrep  # reason: a result object, not a launch
        args=["ydotool"], returncode=returncode, stdout=stdout, stderr=stderr)
    return mock.Mock(return_value=completed)


def test_legacy_banner_is_classified_legacy():
    with mock.patch.object(subprocess, "run", _fake_run(stdout=LEGACY_BANNER)):
        assert _ydotool_cli.cli_generation("/usr/bin/ydotool") == \
            _ydotool_cli.LEGACY


def test_modern_banner_is_classified_modern():
    with mock.patch.object(subprocess, "run", _fake_run(stdout=MODERN_BANNER)):
        assert _ydotool_cli.cli_generation("/usr/bin/ydotool") == \
            _ydotool_cli.MODERN


def test_banner_on_stderr_is_read_too():
    """0.1.8 prints its usage to stderr on some paths; both streams count."""
    with mock.patch.object(subprocess, "run", _fake_run(stderr=LEGACY_BANNER)):
        assert _ydotool_cli.cli_generation("/usr/bin/ydotool") == \
            _ydotool_cli.LEGACY


def test_unrecognised_banner_is_unknown_not_legacy():
    """Only the version measured to fail silently is refused."""
    with mock.patch.object(subprocess, "run",
                           _fake_run(stdout=b"ydotool 3.0\nsomething new\n")):
        assert _ydotool_cli.cli_generation("/usr/bin/ydotool") == \
            _ydotool_cli.UNKNOWN


def test_a_word_containing_recorder_does_not_trigger_the_legacy_verdict():
    """The marker is a whole command name, not a substring of prose."""
    banner = b"Usage: ydotool <cmd>\nAvailable commands:\n  screenrecorder\n"
    with mock.patch.object(subprocess, "run", _fake_run(stdout=banner)):
        assert _ydotool_cli.cli_generation("/usr/bin/ydotool") == \
            _ydotool_cli.UNKNOWN


def test_probe_failure_is_unknown_rather_than_an_accusation():
    with mock.patch.object(subprocess, "run",
                           side_effect=OSError("no such binary")):
        assert _ydotool_cli.cli_generation("/usr/bin/ydotool") == \
            _ydotool_cli.UNKNOWN


def test_probe_timeout_is_unknown():
    with mock.patch.object(
            subprocess, "run",
            side_effect=subprocess.TimeoutExpired(  # nosemgrep  # reason: an exception object, not a launch
                cmd="ydotool", timeout=5.0)):
        assert _ydotool_cli.cli_generation("/usr/bin/ydotool") == \
            _ydotool_cli.UNKNOWN


def test_the_probe_runs_once_per_path():
    """Mouse and key dispatch must not pay a subprocess per event."""
    runner = _fake_run(stdout=MODERN_BANNER)
    with mock.patch.object(subprocess, "run", runner):
        for _ in range(5):
            _ydotool_cli.cli_generation("/usr/bin/ydotool")
    assert runner.call_count == 1


def test_the_cache_is_keyed_on_the_path():
    runner = _fake_run(stdout=MODERN_BANNER)
    with mock.patch.object(subprocess, "run", runner):
        _ydotool_cli.cli_generation("/usr/bin/ydotool")
        _ydotool_cli.cli_generation("/opt/other/ydotool")
    assert runner.call_count == 2


def test_reject_legacy_cli_raises_with_an_actionable_message():
    with mock.patch.object(subprocess, "run", _fake_run(stdout=LEGACY_BANNER)):
        with pytest.raises(AutoControlException) as error:
            _ydotool_cli.reject_legacy_cli("/usr/bin/ydotool")
    message = str(error.value)
    assert "0.1.x" in message
    assert "/usr/bin/ydotool" in message
    # The three routes out: a newer ydotool, or the X11 backend.
    assert "1.0" in message
    assert "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11" in message


def test_reject_legacy_cli_returns_the_path_for_a_modern_tool():
    with mock.patch.object(subprocess, "run", _fake_run(stdout=MODERN_BANNER)):
        assert _ydotool_cli.reject_legacy_cli("/usr/bin/ydotool") == \
            "/usr/bin/ydotool"


def test_reject_legacy_cli_lets_an_unknown_version_through():
    with mock.patch.object(subprocess, "run", _fake_run(stdout=b"???")):
        assert _ydotool_cli.reject_legacy_cli("/usr/bin/ydotool") == \
            "/usr/bin/ydotool"


def test_reset_cache_can_forget_one_path_only():
    runner = _fake_run(stdout=MODERN_BANNER)
    with mock.patch.object(subprocess, "run", runner):
        _ydotool_cli.cli_generation("/a/ydotool")
        _ydotool_cli.cli_generation("/b/ydotool")
        _ydotool_cli.reset_cache("/a/ydotool")
        _ydotool_cli.cli_generation("/a/ydotool")
        _ydotool_cli.cli_generation("/b/ydotool")
    assert runner.call_count == 3


# --------------------------------------------------------------------------
# The two backends have to consult the guard, or it protects nobody.
# --------------------------------------------------------------------------

def test_mouse_refuses_to_emit_through_the_legacy_cli():
    from je_auto_control.linux_wayland import mouse

    with mock.patch("je_auto_control.linux_wayland.mouse.binary_path",
                    return_value="/usr/bin/ydotool"), \
            mock.patch.object(mouse, "_try_libei", return_value=None), \
            mock.patch.object(subprocess, "run", _fake_run(
                stdout=LEGACY_BANNER)):
        with pytest.raises(AutoControlException, match="0.1.x"):
            mouse.click_mouse(mouse.wayland_mouse_left)


def test_keyboard_refuses_to_emit_through_the_legacy_cli():
    from je_auto_control.linux_wayland import keyboard

    with mock.patch("je_auto_control.linux_wayland.keyboard.binary_path",
                    return_value="/usr/bin/ydotool"), \
            mock.patch.object(keyboard, "_try_libei", return_value=None), \
            mock.patch.object(subprocess, "run", _fake_run(
                stdout=LEGACY_BANNER)):
        with pytest.raises(AutoControlException, match="0.1.x"):
            keyboard.press_key(30)


def test_hotkey_refuses_to_emit_through_the_legacy_cli():
    """The chord path builds its argv separately, so it needs its own guard."""
    from je_auto_control.linux_wayland import keyboard

    with mock.patch("je_auto_control.linux_wayland.keyboard.binary_path",
                    return_value="/usr/bin/ydotool"), \
            mock.patch.object(keyboard, "_try_libei", return_value=None), \
            mock.patch.object(subprocess, "run", _fake_run(
                stdout=LEGACY_BANNER)):
        with pytest.raises(AutoControlException, match="0.1.x"):
            keyboard.hotkey([29, 30])


def test_the_install_hints_no_longer_recommend_a_broken_package():
    """`apt install ydotool` gives 0.1.8 on bookworm and nothing on trixie."""
    from je_auto_control.linux_wayland import keyboard, mouse

    for hint in (mouse._INSTALL_HINT, keyboard._INSTALL_HINT_YDOTOOL):
        assert "apt install ydotool" not in hint
        assert "1.0" in hint
