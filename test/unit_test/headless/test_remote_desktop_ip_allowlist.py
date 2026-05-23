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


# --- pure compile / match helpers ---------------------------------------

def test_compile_allowlist_returns_none_for_empty():
    assert _compile_ip_allowlist(None) is None
    assert _compile_ip_allowlist([]) is None
    assert _compile_ip_allowlist([""]) is None


def test_compile_allowlist_keeps_valid_ips():
    compiled = _compile_ip_allowlist(["192.168.1.10", "10.0.0.0/8"])
    assert compiled is not None and len(compiled) == 2


def test_compile_allowlist_drops_garbage_entries():
    compiled = _compile_ip_allowlist(
        ["192.168.1.10", "not-an-ip", "10.0.0.0/8"],
    )
    assert compiled is not None and len(compiled) == 2


def test_ip_in_allowlist_with_no_list_accepts_all():
    assert _ip_in_allowlist(None, "1.2.3.4") is True
    assert _ip_in_allowlist([], "1.2.3.4") is True


def test_ip_in_allowlist_exact_match():
    compiled = _compile_ip_allowlist(["192.168.1.10"])
    assert _ip_in_allowlist(compiled, "192.168.1.10") is True
    assert _ip_in_allowlist(compiled, "192.168.1.11") is False


def test_ip_in_allowlist_cidr_match():
    compiled = _compile_ip_allowlist(["10.0.0.0/8"])
    assert _ip_in_allowlist(compiled, "10.5.5.5") is True
    assert _ip_in_allowlist(compiled, "11.0.0.1") is False


def test_ip_in_allowlist_rejects_unparseable_peer():
    compiled = _compile_ip_allowlist(["10.0.0.0/8"])
    assert _ip_in_allowlist(compiled, "not-a-host") is False


# --- end-to-end: blocked connection drops at accept --------------------

def test_localhost_blocked_when_not_in_allowlist():
    """A loopback viewer must fail when the allowlist only admits a LAN."""
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: _make_jpeg(),
        ip_allowlist=["192.168.0.0/16"],  # localhost is NOT in this range
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
