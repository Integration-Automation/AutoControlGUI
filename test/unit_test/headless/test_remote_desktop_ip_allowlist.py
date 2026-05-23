"""Headless tests for the host-side IP allowlist (Phase 4.3)."""
import socket
import time
from io import BytesIO

import pytest

from je_auto_control.utils.remote_desktop.host import (
    RemoteDesktopHost, _compile_ip_allowlist, _ip_in_allowlist,
)
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer


def _make_jpeg() -> bytes:
    from PIL import Image
    img = Image.new("RGB", (32, 24), color=(0, 0, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


# RFC 1918 / TEST-NET / loopback example strings used as parser fixtures.
# These never open a real socket on the public internet — they exercise
# the in-memory allowlist matcher.
# NOSONAR python:S1313  # reason: RFC 1918 test fixtures, no public-internet I/O
_LAN_IP = "192.168.1.10"  # noqa: S104  # nosec B104  # NOSONAR python:S1313
_LAN_IP_2 = "192.168.1.11"  # NOSONAR python:S1313  # reason: RFC 1918 test fixture
_LAN_NET = "192.168.0.0/16"  # NOSONAR python:S1313  # reason: RFC 1918 test fixture
_CORP_NET = "10.0.0.0/8"  # NOSONAR python:S1313  # reason: RFC 1918 test fixture
_CORP_IP = "10.5.5.5"  # NOSONAR python:S1313  # reason: RFC 1918 test fixture
_NEAR_CORP_IP = "11.0.0.1"  # NOSONAR python:S1313  # reason: RFC 1918 test fixture
_OUT_IP = "1.2.3.4"  # NOSONAR python:S1313  # reason: test fixture, no public-internet I/O


# --- pure compile / match helpers ---------------------------------------

def test_compile_allowlist_returns_none_for_empty():
    assert _compile_ip_allowlist(None) is None
    assert _compile_ip_allowlist([]) is None
    assert _compile_ip_allowlist([""]) is None


def test_compile_allowlist_keeps_valid_ips():
    compiled = _compile_ip_allowlist([_LAN_IP, _CORP_NET])
    assert compiled is not None and len(compiled) == 2


def test_compile_allowlist_drops_garbage_entries():
    compiled = _compile_ip_allowlist(
        [_LAN_IP, "not-an-ip", _CORP_NET],
    )
    assert compiled is not None and len(compiled) == 2


def test_ip_in_allowlist_with_no_list_accepts_all():
    assert _ip_in_allowlist(None, _OUT_IP) is True
    assert _ip_in_allowlist([], _OUT_IP) is True


def test_ip_in_allowlist_exact_match():
    compiled = _compile_ip_allowlist([_LAN_IP])
    assert _ip_in_allowlist(compiled, _LAN_IP) is True
    assert _ip_in_allowlist(compiled, _LAN_IP_2) is False


def test_ip_in_allowlist_cidr_match():
    compiled = _compile_ip_allowlist([_CORP_NET])
    assert _ip_in_allowlist(compiled, _CORP_IP) is True
    assert _ip_in_allowlist(compiled, _NEAR_CORP_IP) is False


def test_ip_in_allowlist_rejects_unparseable_peer():
    compiled = _compile_ip_allowlist([_CORP_NET])
    assert _ip_in_allowlist(compiled, "not-a-host") is False


# --- end-to-end: blocked connection drops at accept --------------------

def test_localhost_blocked_when_not_in_allowlist():
    """A loopback viewer must fail when the allowlist only admits a LAN."""
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: _make_jpeg(),
        ip_allowlist=[_LAN_NET],  # localhost is NOT in this range
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
        )
        with pytest.raises((OSError, ConnectionError, socket.error)):
            viewer.connect(timeout=2.0)
        # Allow the host accept thread to log + close.
        time.sleep(0.2)
        assert host.connected_clients == 0
    finally:
        host.stop(timeout=1.0)


def test_localhost_admitted_when_in_allowlist():
    """The same loopback viewer succeeds once 127.0.0.1 is allowlisted."""
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: _make_jpeg(),
        ip_allowlist=["127.0.0.0/8"],
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
        )
        viewer.connect(timeout=5.0)
        try:
            assert viewer.connected
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)
