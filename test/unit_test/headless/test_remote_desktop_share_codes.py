"""Phase 4.2: single-use share-code tests."""
import time
from io import BytesIO

import pytest

from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.protocol import (
    AuthenticationError,
)
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer


def _make_jpeg() -> bytes:
    from PIL import Image
    img = Image.new("RGB", (32, 24), color=(0, 200, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def test_share_code_admits_a_viewer():
    host = RemoteDesktopHost(
        token="main", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: _make_jpeg(),
        single_use_tokens=["abc123"],
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="abc123",
        )
        viewer.connect(timeout=5.0)
        try:
            assert viewer.connected
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_share_code_is_consumed_after_first_use():
    """A second connect with the same code must fail."""
    host = RemoteDesktopHost(
        token="main", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: _make_jpeg(),
        single_use_tokens=["abc123"],
    )
    host.start()
    try:
        first = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="abc123",
        )
        first.connect(timeout=5.0)
        first.disconnect(timeout=1.0)
        time.sleep(0.2)
        second = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="abc123",
        )
        with pytest.raises((AuthenticationError, OSError, ConnectionError)):
            second.connect(timeout=2.0)
    finally:
        host.stop(timeout=1.0)


def test_main_token_still_works_alongside_share_codes():
    host = RemoteDesktopHost(
        token="main", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: _make_jpeg(),
        single_use_tokens=["abc123"],
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="main",
        )
        viewer.connect(timeout=5.0)
        try:
            assert viewer.connected
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_add_and_revoke_share_codes_runtime():
    host = RemoteDesktopHost(
        token="main", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: _make_jpeg(),
    )
    host.start()
    try:
        host.add_single_use_token("rotating")
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="rotating",
        )
        viewer.connect(timeout=5.0)
        viewer.disconnect(timeout=1.0)
        # Add then revoke before use: revoked code must not work.
        host.add_single_use_token("nope")
        assert host.revoke_single_use_token("nope") is True
        viewer2 = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="nope",
        )
        with pytest.raises((AuthenticationError, OSError, ConnectionError)):
            viewer2.connect(timeout=2.0)
    finally:
        host.stop(timeout=1.0)


def test_add_single_use_token_rejects_empty():
    host = RemoteDesktopHost(
        token="main", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: _make_jpeg(),
    )
    with pytest.raises(ValueError):
        host.add_single_use_token("")
