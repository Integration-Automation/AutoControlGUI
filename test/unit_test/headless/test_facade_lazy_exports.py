"""Public discovery and protocol imports must not initialize unrelated features."""

from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]

OPTIONAL_GROUPS = (
    ("webrtc_host", ("WebRTCDesktopHost", "WebRTCDesktopViewer", "WebRTCConfig")),
    ("session_recorder", ("SessionRecorder",)),
    ("multi_viewer", ("MultiViewerHost",)),
    ("webrtc_mic", ("MicUplinkSender", "MicUplinkReceiver")),
    ("webrtc_files", ("FileTransferSender", "FileTransferReceiver", "FileTransferWebRTCError")),
    ("hw_codec", ("available_hardware_codecs", "active_hardware_codec",
                  "install_hardware_codec", "uninstall_hardware_codec")),
)


def _run_child(program: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(program)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("include_protocol", [False, True])
def test_discovery_does_not_attempt_optional_feature_imports(include_protocol):
    """Observe actual import attempts without making installed dependencies unavailable."""
    program = '''
import sys

watched = ("av", "aiortc", "numpy", "PySide6", "cv2", "mss",
           "je_auto_control.gui", "je_auto_control.utils.agent_runtime",
           "je_auto_control.utils.executor")
attempts = []

class Observer:
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == prefix or fullname.startswith(prefix + ".") for prefix in watched):
            attempts.append(fullname)
        return None

sys.meta_path.insert(0, Observer())
import je_auto_control as ac
assert set(ac.__all__).issubset(dir(ac))
assert callable(ac.start_autocontrol_gui)
if INCLUDE_PROTOCOL:
    from je_auto_control.utils.remote_desktop import webrtc_file_commit
    from je_auto_control.utils import remote_desktop
    assert set(remote_desktop.__all__).issubset(dir(remote_desktop))
    assert callable(webrtc_file_commit.bind_commit_channel)
assert not attempts, attempts
'''
    _run_child(program.replace("INCLUDE_PROTOCOL", repr(include_protocol)))


@pytest.mark.parametrize("child_first", [False, True])
def test_remote_module_and_singleton_exports_preserve_identity(child_first):
    """Both supported import orders expose the existing singleton and real child module."""
    program = '''
import importlib
from types import ModuleType

if CHILD_FIRST:
    owner = importlib.import_module("je_auto_control.utils.remote_desktop.registry")
from je_auto_control.utils import remote_desktop as rd
from je_auto_control.utils.remote_desktop import registry, signaling_client
owner = importlib.import_module("je_auto_control.utils.remote_desktop.registry")
assert isinstance(owner, ModuleType)
assert registry is rd.registry is owner.registry
assert signaling_client is importlib.import_module("je_auto_control.utils.remote_desktop.signaling_client")
from je_auto_control import remote_desktop_registry, RemoteDesktopAuthError
from je_auto_control.utils.remote_desktop.protocol import AuthenticationError
assert remote_desktop_registry is registry
assert RemoteDesktopAuthError is AuthenticationError
rd.WebRTCDesktopHost = None
assert rd.is_webrtc_available() is False
rd.WebRTCDesktopHost = object()
assert rd.is_webrtc_available() is True
'''
    _run_child(program.replace("CHILD_FIRST", repr(child_first)))


@pytest.mark.parametrize("owner,names", OPTIONAL_GROUPS)
@pytest.mark.parametrize("unexpected_error", [False, True])
def test_optional_group_failure_is_cached_only_for_import_error(owner, names, unexpected_error):
    """Missing optional features stay unavailable; other failures propagate and can retry."""
    program = '''
import sys

target = "je_auto_control.utils.remote_desktop." + OWNER
names = NAMES
attempts = []

class Failure:
    error = RuntimeError if UNEXPECTED_ERROR else ImportError

    def find_spec(self, fullname, path=None, target=None):
        if fullname == globals()["target"]:
            attempts.append(fullname)
            raise self.error("optional dependency failure")
        return None

failure = Failure()
sys.meta_path.insert(0, failure)
from je_auto_control.utils import remote_desktop as rd
assert not attempts, attempts
if UNEXPECTED_ERROR:
    try:
        getattr(rd, names[0])
    except RuntimeError:
        pass
    else:
        raise AssertionError("unexpected import failure was swallowed")
    assert attempts == [target], attempts
    failure.error = ImportError
assert all(getattr(rd, name) is None for name in names)
expected_attempts = 2 if UNEXPECTED_ERROR else 1
assert len(attempts) == expected_attempts, attempts
assert all(getattr(rd, name) is None for name in reversed(names))
assert len(attempts) == expected_attempts, attempts
'''
    program = program.replace("OWNER", repr(owner)).replace("NAMES", repr(names))
    _run_child(program.replace("UNEXPECTED_ERROR", repr(unexpected_error)))
