"""Native crash probes must distinguish measured outcomes from probe failures."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
from types import ModuleType, SimpleNamespace

import pytest

from je_auto_control.linux_wayland.permission import WaylandPermissionRequired


ROOT = Path(__file__).resolve().parents[3]


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "docker" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_native_portal_closure_preserves_typed_permission_failure():
    module = _load('portal_verify')

    def closed(**_kwargs):
        raise WaylandPermissionRequired('input', 'the desktop portal closed the remote-desktop session')

    detail = module._check_portal_closed(SimpleNamespace(connect_eis_fd=closed))
    assert 'closed' in detail


@pytest.mark.parametrize('state,capability', [('unsupported', 'input'), ('needs_permission', 'capture')])
def test_native_portal_closure_rejects_incorrect_capability_state(state, capability):
    module = _load('portal_verify')

    def closed(**_kwargs):
        failure = WaylandPermissionRequired(capability, 'the desktop portal closed the remote-desktop session')
        failure.state = state
        raise failure

    with pytest.raises(AssertionError, match='permission state'):
        module._check_portal_closed(SimpleNamespace(connect_eis_fd=closed))


@pytest.mark.parametrize("name", ["libei_verify", "eis_verify"])
@pytest.mark.parametrize("returncode", [1, -6])
def test_failed_native_probe_is_not_reported_as_a_pass(monkeypatch, name, returncode):
    """Import/connection errors and other signals prove neither cleanup nor safety."""
    module = _load(name)
    result = subprocess.CompletedProcess([], returncode, b"", b"probe setup failed")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)
    probe = module._check_unref_sentinel if name == "libei_verify" else module._live_teardown_sentinel
    with pytest.raises(AssertionError, match="probe setup failed"):
        probe("/tmp/sentinel-test")


@pytest.mark.parametrize("name", ["libei_verify", "eis_verify"])
def test_successful_native_probe_requires_the_post_unref_marker(monkeypatch, name):
    """Exit zero without reaching unref is not native teardown evidence."""
    module = _load(name)
    result = subprocess.CompletedProcess([], 0, b"", b"")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)
    probe = module._check_unref_sentinel if name == "libei_verify" else module._live_teardown_sentinel
    with pytest.raises(AssertionError, match="survived"):
        probe("/tmp/sentinel-test")


def test_half_open_native_crash_requires_the_pre_unref_marker(monkeypatch):
    """An earlier ctypes crash must not be attributed to ei_unref."""
    module = _load("libei_verify")
    result = subprocess.CompletedProcess([], -11, b"", b"setup crashed")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)
    with pytest.raises(AssertionError, match="setup crashed"):
        module._check_unref_sentinel("/tmp/sentinel-test")


def test_expected_half_open_crash_is_classified_and_probe_is_bounded(monkeypatch):
    """The known half-open SIGSEGV is a measured classification, with a deadline."""
    module = _load("libei_verify")
    calls = []

    def run(*_args, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess([], -11, b"before_unref\n", b"native traceback")

    monkeypatch.setattr(subprocess, "run", run)
    assert "segfaults" in module._check_unref_sentinel("/tmp/sentinel-test")
    assert calls[0]["timeout"] <= 60


@pytest.mark.parametrize("name", ["libei_verify", "eis_verify"])
def test_measured_safe_native_cleanup_passes(monkeypatch, name):
    """Both probes accept a bounded successful run that reached the release."""
    module = _load(name)
    result = subprocess.CompletedProcess([], 0, b"before_unref\nsurvived\n", b"")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)
    probe = module._check_unref_sentinel if name == "libei_verify" else module._live_teardown_sentinel
    assert probe("/tmp/sentinel-test")


def test_crash_on_a_live_context_fails_the_native_verification(monkeypatch, capfd):
    """A known crash after the handshake is never accepted as safe cleanup."""
    module = _load("eis_verify")
    result = subprocess.CompletedProcess([], -11, b"before_unref\n", b"native traceback")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)
    with pytest.raises(AssertionError, match="segfaults on a live context"):
        module._live_teardown_sentinel("/tmp/sentinel-test")
    assert "native traceback" in capfd.readouterr().out
