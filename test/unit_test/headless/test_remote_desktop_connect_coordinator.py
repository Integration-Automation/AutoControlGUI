"""Headless tests for the Remote Desktop transport coordinator."""
import pytest

from je_auto_control.utils.remote_desktop.connect_coordinator import (
    ConnectTarget, UnresolvableTargetError, parse_target,
)


# --- TCP direct ---------------------------------------------------------

def test_parse_bare_host_port_is_tcp():
    target = parse_target("192.168.1.10:5555")
    assert target.kind == "tcp"
    assert target.host == "192.168.1.10"
    assert target.port == 5555
    assert target.is_direct


def test_parse_tcp_scheme_strips_prefix():
    target = parse_target("tcp://example.com:5555")
    assert target == ConnectTarget(kind="tcp", host="example.com", port=5555)


def test_parse_tcp_with_whitespace():
    target = parse_target("  127.0.0.1:1234  ")
    assert target.host == "127.0.0.1"
    assert target.port == 1234


# --- WebSocket ----------------------------------------------------------

def test_parse_ws_scheme_keeps_default_path():
    target = parse_target("ws://host:8765")
    assert target.kind == "ws"
    assert target.host == "host"
    assert target.port == 8765
    assert target.path == "/"


def test_parse_ws_scheme_keeps_custom_path():
    target = parse_target("ws://host:8765/api/desktop")
    assert target.kind == "ws"
    assert target.path == "/api/desktop"


def test_parse_wss_scheme():
    target = parse_target("wss://example.com:443/foo")
    assert target.kind == "wss"
    assert target.host == "example.com"
    assert target.port == 443
    assert target.path == "/foo"


# --- WebRTC 9-digit ID --------------------------------------------------

def test_parse_nine_digit_id_is_webrtc():
    target = parse_target("123456789")
    assert target.kind == "webrtc_id"
    assert target.host_id == "123456789"
    assert not target.is_direct


def test_parse_dashed_id_normalises():
    target = parse_target("123-456-789")
    assert target.kind == "webrtc_id"
    assert target.host_id == "123456789"


def test_parse_spaced_id_normalises():
    target = parse_target("123 456 789")
    assert target.kind == "webrtc_id"
    assert target.host_id == "123456789"


def test_parse_underscore_id_normalises():
    target = parse_target("123_456_789")
    assert target.kind == "webrtc_id"
    assert target.host_id == "123456789"


# --- error cases --------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "",
    "   ",
    "no-port",
    "host:abc",
    "host:0",
    "host:70000",
    ":1234",
    "ws://host",  # missing port
    "ws://:8765",  # missing host
    "1234",  # too few digits, not an ID
    "12345678901",  # too many digits, not an ID
])
def test_parse_target_rejects_bad_input(bad):
    with pytest.raises(UnresolvableTargetError):
        parse_target(bad)


def test_parse_target_rejects_non_string():
    with pytest.raises(UnresolvableTargetError):
        parse_target(12345)  # type: ignore[arg-type]


# --- discriminator helpers ---------------------------------------------

def test_is_direct_matches_kind():
    assert ConnectTarget(kind="tcp").is_direct
    assert ConnectTarget(kind="ws").is_direct
    assert ConnectTarget(kind="wss").is_direct
    assert not ConnectTarget(kind="webrtc_id").is_direct
