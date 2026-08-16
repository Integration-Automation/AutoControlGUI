"""Headless tests for the "will my input arrive?" probes. No Qt."""
import time

import pytest

import je_auto_control as ac
from je_auto_control.utils.input_reach import input_reach as reach


@pytest.fixture(autouse=True)
def _clear_cache():
    reach._desktop_cache = None
    yield
    reach._desktop_cache = None


def test_desktop_probe_is_cached_then_expires(monkeypatch):
    # Input primitives ask constantly, so it must be cached — but not for so
    # long that an unlocked machine still reports locked.
    monkeypatch.setattr(reach.sys, "platform", "win32")
    reach._desktop_cache = (time.monotonic(), False)
    assert reach.input_desktop_available() is False
    reach._desktop_cache = (time.monotonic() - reach.DESKTOP_CACHE_SEC - 1, False)
    assert reach.input_desktop_available() is not False


def test_desktop_probe_is_true_off_windows(monkeypatch):
    monkeypatch.setattr(reach.sys, "platform", "linux")
    assert reach.input_desktop_available() is True


def test_reach_probe_is_true_off_windows(monkeypatch):
    monkeypatch.setattr(reach.sys, "platform", "linux")
    assert reach.input_reaches_system() is True


def test_reach_probe_uses_a_key_nothing_listens_for():
    # F13: real keyboards stop at F12, so the probe cannot trigger anything.
    assert reach.PROBE_VK == 0x7C


def test_executor_adapter_skips_the_keystroke_when_the_desktop_is_locked(monkeypatch):
    # No point sending a probe key at a lock screen, and no point pretending
    # the answer is yes.
    from je_auto_control.utils.executor import action_executor

    import je_auto_control.utils.input_reach as package

    sent = []
    # The adapter imports these from the package namespace, so that is what has
    # to be patched — patching the module underneath would let the real probe
    # run and actually press a key.
    monkeypatch.setattr(package, "input_desktop_available", lambda: False)
    monkeypatch.setattr(package, "input_reaches_system",
                        lambda *a, **k: sent.append(1) or True)
    result = action_executor._input_reachable()
    assert result == {"desktop_available": False, "reaches_system": False}
    assert sent == []


def test_executor_adapter_probes_when_the_desktop_is_available(monkeypatch):
    from je_auto_control.utils.executor import action_executor

    import je_auto_control.utils.input_reach as package

    monkeypatch.setattr(package, "input_desktop_available", lambda: True)
    monkeypatch.setattr(package, "input_reaches_system", lambda *a, **k: False)
    assert action_executor._input_reachable() == {
        "desktop_available": True, "reaches_system": False}


def test_wiring():
    assert "AC_input_reachable" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_input_reachable" in {t.name for t in build_default_tool_registry()}
    for attr in ("input_desktop_available", "input_reaches_system"):
        assert hasattr(ac, attr) and attr in ac.__all__
