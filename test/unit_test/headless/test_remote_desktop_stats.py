"""Phase 1.2: viewer-side rolling stats tests."""
import threading
import time
from io import BytesIO

import pytest

from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer


def _make_jpeg(seed: int) -> bytes:
    from PIL import Image
    img = Image.new("RGB", (32, 24), color=(seed % 256, 0, 0))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def test_stats_zero_before_any_frame():
    viewer = RemoteDesktopViewer(host="127.0.0.1", port=1, token="t")
    snap = viewer.stats()
    assert snap == {
        "fps": 0.0, "kbps": 0.0, "frames": 0.0, "bytes": 0.0, "uptime": 0.0,
    }


def test_stats_records_received_frames():
    counter = {"n": 0}

    def provider():
        counter["n"] += 1
        return _make_jpeg(counter["n"])

    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=20.0,
        frame_provider=provider,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
        )
        viewer.connect(timeout=5.0)
        try:
            # Let a handful of frames accumulate.
            deadline = time.monotonic() + 2.0
            while viewer.stats()["frames"] < 5 and time.monotonic() < deadline:
                time.sleep(0.05)
            snap = viewer.stats()
            assert snap["frames"] >= 5
            assert snap["bytes"] > 0
            assert snap["uptime"] > 0
            assert snap["fps"] > 0
            assert snap["kbps"] > 0
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)
