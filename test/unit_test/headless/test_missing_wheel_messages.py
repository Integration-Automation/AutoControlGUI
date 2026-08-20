"""A missing arm64 wheel must say so, not raise ModuleNotFoundError. No Qt.

`cryptography`, `opencv-python` and `je_open_cv` publish no `win_arm64`
wheel, so `pyproject.toml` marks them off that one platform and everything
else in the package keeps working there. That trade is only honest if the
features that *do* need them fail legibly: on Windows arm64 the package is
installed and correct, so a bare `ModuleNotFoundError: No module named 'cv2'`
reads like a broken install and sends the user to reinstall something that
cannot exist.

These tests make the missing import fail on a machine that has the wheels,
by putting `None` in `sys.modules` — the import system raises `ImportError`
for that, which is the branch the accessors catch.
"""
import importlib
import os
import pathlib
import subprocess
import sys
from typing import Callable

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _blocked(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Make importing each of ``names`` raise ImportError."""
    for name in names:
        monkeypatch.setitem(sys.modules, name, None)


def test_the_secret_vault_names_the_wheel_it_needs(monkeypatch) -> None:
    """SecretManager.initialize explains cryptography rather than failing raw."""
    from je_auto_control.utils.secrets import secret_store

    _blocked(monkeypatch, "cryptography.fernet")
    with pytest.raises(RuntimeError) as caught:
        secret_store._fernet_types()

    message = str(caught.value)
    assert "cryptography" in message
    assert "Windows arm64" in message
    assert isinstance(caught.value.__cause__, ImportError)


def test_action_encryption_names_the_wheel_it_needs(monkeypatch) -> None:
    """Action-file encryption explains cryptography rather than failing raw."""
    from je_auto_control.utils.action_signing import cipher

    _blocked(monkeypatch, "cryptography.fernet")
    with pytest.raises(RuntimeError) as caught:
        cipher._fernet_types()

    message = str(caught.value)
    assert "cryptography" in message
    assert "Windows arm64" in message
    assert isinstance(caught.value.__cause__, ImportError)


def test_encrypting_an_action_file_surfaces_the_same_message(
        monkeypatch, tmp_path) -> None:
    """The public entry point carries the message, not just the accessor."""
    from je_auto_control.utils.action_signing import cipher

    script = tmp_path / "script.json"
    script.write_text('[["AC_noop"]]', encoding="utf-8")

    _blocked(monkeypatch, "cryptography.fernet")
    with pytest.raises(RuntimeError, match="Windows arm64"):
        cipher.encrypt_action_file(script, b"unit-test-key")


@pytest.mark.parametrize("accessor_name,blocked,needle", [
    ("require_cv2", "cv2", "opencv-python"),
    ("require_je_open_cv", "je_open_cv", "je_open_cv"),
])
def test_the_image_stack_doors_name_their_wheel(
        monkeypatch, accessor_name: str, blocked: str, needle: str) -> None:
    """Both image-stack accessors explain the platform, not just the module."""
    from je_auto_control.utils.cv2_utils import optional

    accessor: Callable = getattr(optional, accessor_name)
    _blocked(monkeypatch, blocked)
    with pytest.raises(RuntimeError) as caught:
        accessor()

    message = str(caught.value)
    assert needle in message
    assert "Windows arm64" in message
    assert isinstance(caught.value.__cause__, ImportError)


def test_the_accessors_return_the_real_modules_when_the_wheels_are_there() -> None:
    """A lazy import placed in the wrong branch must not pass as a win."""
    pytest.importorskip("cv2")
    from je_auto_control.utils.cv2_utils.optional import require_cv2

    assert require_cv2() is importlib.import_module("cv2")


# The four modules that import cryptography at module scope are not on the
# facade's import path, so they keep a module-scope import — what they must
# not do is fail with a bare ModuleNotFoundError. Checked in a subprocess
# because the import has to happen with the module genuinely absent.
_PROBE = """
import sys


class Blocker:
    def find_module(self, name, path=None):
        return self.find_spec(name, path)

    def find_spec(self, name, path=None, target=None):
        if name == "cryptography" or name.startswith("cryptography."):
            raise ImportError("blocked for probe: " + name)
        return None


sys.meta_path.insert(0, Blocker())
for name in [m for m in sys.modules if m.split(".")[0] == "cryptography"]:
    del sys.modules[name]

try:
    import je_auto_control.utils.tls_acme.keys  # noqa: F401
except ImportError as error:
    print(str(error))
else:
    raise SystemExit("expected ImportError, module imported cleanly")
"""


def test_a_module_scope_importer_explains_itself() -> None:
    """tls_acme.keys re-raises with the reason, following webrtc_transport."""
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    finished = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, timeout=120, env=env, check=False,
    )
    assert finished.returncode == 0, finished.stderr
    assert "Windows arm64" in finished.stdout, finished.stdout
    assert "cryptography" in finished.stdout, finished.stdout
