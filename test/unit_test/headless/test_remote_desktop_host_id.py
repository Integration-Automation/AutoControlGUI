"""Tests for the persistent host-ID and the AUTH_OK handshake extension."""
import time
from pathlib import Path

import pytest

from je_auto_control.utils.remote_desktop import (
    RemoteDesktopHost, RemoteDesktopViewer,
)
from je_auto_control.utils.remote_desktop.host_id import (
    HostIdError, format_host_id, generate_host_id, load_or_create_host_id,
    parse_host_id, validate_host_id,
)
from je_auto_control.utils.remote_desktop.protocol import AuthenticationError


def _wait_until(predicate, timeout: float = 2.0,
                interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_generate_host_id_is_nine_digits():
    value = generate_host_id()
    assert isinstance(value, str)
    assert len(value) == 9
    assert value.isdigit()


def test_validate_host_id_accepts_valid_id():
    assert validate_host_id("123456789") == "123456789"


def test_validate_host_id_rejects_short_id():
    with pytest.raises(HostIdError):
        validate_host_id("12345")


def test_validate_host_id_rejects_alpha():
    with pytest.raises(HostIdError):
        validate_host_id("12345abcd")


def test_format_host_id_groups_in_threes():
    assert format_host_id("123456789") == "123 456 789"


def test_parse_host_id_strips_whitespace_and_separators():
    assert parse_host_id("123 456 789") == "123456789"
    assert parse_host_id("123-456-789") == "123456789"
    assert parse_host_id("123_456_789") == "123456789"


def test_parse_host_id_rejects_garbage():
    with pytest.raises(HostIdError):
        parse_host_id("hello-world")


def test_load_or_create_persists_across_calls(tmp_path: Path):
    target = tmp_path / "host_id"
    first = load_or_create_host_id(target)
    second = load_or_create_host_id(target)
    assert first == second
    assert target.read_text(encoding="utf-8").strip() == first


def test_load_or_create_regenerates_corrupt_file(tmp_path: Path):
    target = tmp_path / "host_id"
    target.write_text("not-a-valid-id", encoding="utf-8")
    new_id = load_or_create_host_id(target)
    assert new_id.isdigit() and len(new_id) == 9
    # Corrupt content was rewritten with the new valid ID.
    assert target.read_text(encoding="utf-8").strip() == new_id


def test_host_exposes_host_id():
    host = RemoteDesktopHost(token="t", host_id="111222333")
    assert host.host_id == "111222333"


def test_host_rejects_invalid_host_id():
    with pytest.raises(HostIdError):
        RemoteDesktopHost(token="t", host_id="abc")


def _start_loopback_host(host_id: str = "987654321") -> RemoteDesktopHost:
    host = RemoteDesktopHost(
        token="tok", bind="127.0.0.1", port=0, fps=50.0,
        frame_provider=lambda: b"frame",
        input_dispatcher=lambda *_args, **_kwargs: None,
        host_id=host_id,
    )
    host.start()
    return host


def test_viewer_receives_host_id_in_auth_ok():
    host = _start_loopback_host("555666777")
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
        )
        viewer.connect(timeout=2.0)
        assert _wait_until(lambda: viewer.remote_host_id == "555666777")
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


def test_expected_host_id_matches_connects_normally():
    host = _start_loopback_host("123123123")
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
            expected_host_id="123123123",
        )
        viewer.connect(timeout=2.0)
        assert viewer.connected
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


def test_expected_host_id_mismatch_raises():
    host = _start_loopback_host("100000001")
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
            expected_host_id="999999999",
        )
        with pytest.raises(AuthenticationError):
            viewer.connect(timeout=2.0)
    finally:
        host.stop(timeout=1.0)


def test_registry_host_status_reports_host_id():
    from je_auto_control.utils.remote_desktop.registry import registry

    registry.disconnect_viewer()
    registry.stop_host()
    try:
        registry.start_host(token="tok", port=0, fps=30.0,
                            host_id="222333444")
        status = registry.host_status()
        assert status["host_id"] == "222333444"
        assert status["running"] is True
    finally:
        registry.stop_host()
