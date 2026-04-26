"""Tests for the AC_remote_* executor commands and registry singleton."""
import time

import pytest

from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.remote_desktop.registry import registry


@pytest.fixture(autouse=True)
def reset_registry():
    """Tear down any leftover host/viewer before and after each test."""
    registry.disconnect_viewer()
    registry.stop_host()
    yield
    registry.disconnect_viewer()
    registry.stop_host()


def _wait_until(predicate, timeout: float = 2.0,
                interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_known_commands_include_remote_desktop():
    assert "AC_start_remote_host" in executor.known_commands()
    assert "AC_stop_remote_host" in executor.known_commands()
    assert "AC_remote_host_status" in executor.known_commands()
    assert "AC_remote_connect" in executor.known_commands()
    assert "AC_remote_disconnect" in executor.known_commands()
    assert "AC_remote_viewer_status" in executor.known_commands()
    assert "AC_remote_send_input" in executor.known_commands()


def test_start_host_then_status_via_executor():
    captured = []

    def stub_provider() -> bytes:
        return b"test-frame"

    # Reach into the registry to install a stub provider so this test
    # never touches PIL.ImageGrab; mirrors what GUI would do for a fake.
    from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost

    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=50.0, quality=70,
        frame_provider=stub_provider, input_dispatcher=captured.append,
    )
    host.start()
    registry._host = host  # noqa: SLF001  # test-only injection

    record = executor.execute_action([["AC_remote_host_status"]])
    status_value = next(iter(record.values()))
    assert status_value["running"] is True
    assert status_value["port"] > 0


def test_start_host_with_blank_token_records_error():
    record = executor.execute_action([
        ["AC_start_remote_host", {"token": ""}],
    ])
    assert any("ValueError" in repr(v) for v in record.values())


def test_send_input_without_viewer_records_connection_error():
    record = executor.execute_action([
        ["AC_remote_send_input", {"action": {"action": "ping"}}],
    ])
    assert any("ConnectionError" in repr(v) for v in record.values())


def test_remote_round_trip_through_executor():
    """Start host + connect viewer + send input via executor commands."""
    record = executor.execute_action([
        ["AC_start_remote_host", {
            "token": "tok", "bind": "127.0.0.1", "port": 0,
            "fps": 50, "quality": 70,
        }],
    ])
    start_status = next(iter(record.values()))
    assert start_status["running"] is True
    port = start_status["port"]
    assert port > 0

    # Replace the default frame provider (PIL.ImageGrab) with a stub so
    # the test does not depend on a real screen being available.
    registry._host._frame_provider = lambda: b"executor-frame"  # noqa: SLF001
    captured = []
    registry._host._dispatch = captured.append  # noqa: SLF001

    executor.execute_action([
        ["AC_remote_connect", {
            "host": "127.0.0.1", "port": port, "token": "tok",
        }],
    ])
    viewer_status = registry.viewer_status()
    assert viewer_status["connected"] is True
    assert _wait_until(lambda: registry.host.connected_clients == 1)

    executor.execute_action([
        ["AC_remote_send_input", {
            "action": {"action": "mouse_move", "x": 5, "y": 7},
        }],
    ])
    assert _wait_until(lambda: captured == [
        {"action": "mouse_move", "x": 5, "y": 7}
    ])

    executor.execute_action([["AC_remote_disconnect"]])
    assert registry.viewer_status()["connected"] is False
    executor.execute_action([["AC_stop_remote_host"]])
    assert registry.host_status()["running"] is False
