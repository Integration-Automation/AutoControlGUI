"""Phase 1.3: lightweight TCP-path session recorder.

The existing :mod:`session_recorder` writes mp4 via PyAV — useful for the
WebRTC path but unusable on stock installs without the ``[webrtc]``
extra. ``JpegSequenceRecorder`` is the no-deps fallback for the TCP /
WebSocket flow: each received JPEG payload is written to disk verbatim,
plus a ``manifest.json`` listing timestamps so a viewer can replay at
original cadence.

Usage::

    rec = JpegSequenceRecorder("~/recordings/2026-05-23")
    rec.start()
    viewer = RemoteDesktopViewer(..., on_frame=rec.record_frame)
    ...
    rec.stop()
    print(rec.manifest_path)  # → ~/recordings/2026-05-23/manifest.json

Thread-safe: ``record_frame`` is callable from the receiver thread while
``stop`` is called from the GUI thread.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional


_MANIFEST_FILENAME = "manifest.json"


class JpegSequenceRecorder:
    """Append-only JPEG-sequence recorder.

    Each call to :meth:`record_frame` writes one numbered .jpg file and
    appends a manifest entry. :meth:`stop` is idempotent and flushes
    the manifest. Caller is responsible for connecting the recorder's
    ``record_frame`` to the viewer's ``on_frame`` callback.
    """

    def __init__(self, output_dir: str, *,
                 file_prefix: str = "frame", digits: int = 6) -> None:
        self._dir = Path(os.path.expanduser(output_dir))
        self._prefix = file_prefix
        self._digits = max(1, int(digits))
        self._lock = threading.Lock()
        self._entries: List[Dict[str, float]] = []
        self._counter = 0
        self._started = False
        self._stopped = False
        self._started_at: Optional[float] = None

    @property
    def output_dir(self) -> Path:
        return self._dir

    @property
    def manifest_path(self) -> Path:
        return self._dir / _MANIFEST_FILENAME

    @property
    def frame_count(self) -> int:
        with self._lock:
            return self._counter

    def start(self) -> None:
        """Create the output directory and reset the manifest buffer."""
        with self._lock:
            if self._started:
                raise RuntimeError("recorder already started")
            self._dir.mkdir(parents=True, exist_ok=True)
            self._entries = []
            self._counter = 0
            self._started = True
            self._stopped = False
            self._started_at = time.time()

    def record_frame(self, payload: bytes) -> None:
        """Write a single JPEG payload to disk; append manifest entry."""
        if not isinstance(payload, (bytes, bytearray)):
            return
        with self._lock:
            if not self._started or self._stopped:
                return
            self._counter += 1
            filename = (
                f"{self._prefix}_{self._counter:0{self._digits}d}.jpg"
            )
            entry = {
                "filename": filename,
                "timestamp": time.time(),
                "size": len(payload),
            }
            target = self._dir / filename
            entries = self._entries
            entries.append(entry)
        # File I/O outside the lock so concurrent writers don't serialise.
        try:
            target.write_bytes(bytes(payload))
        except OSError:
            # Roll back the manifest entry so it stays consistent with disk.
            with self._lock:
                if entries and entries[-1] is entry:
                    entries.pop()
                    self._counter -= 1

    def stop(self) -> Path:
        """Flush manifest.json and return its path. Idempotent."""
        with self._lock:
            if not self._started:
                raise RuntimeError("recorder was never started")
            if self._stopped:
                return self.manifest_path
            self._stopped = True
            manifest = {
                "started_at": self._started_at,
                "stopped_at": time.time(),
                "frame_count": self._counter,
                "entries": list(self._entries),
            }
        try:
            self.manifest_path.write_text(
                json.dumps(manifest, indent=2), encoding="utf-8",
            )
        except OSError:
            pass
        return self.manifest_path


def load_manifest(path) -> Dict:
    """Read a manifest.json written by :class:`JpegSequenceRecorder`."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


__all__ = ["JpegSequenceRecorder", "load_manifest"]
