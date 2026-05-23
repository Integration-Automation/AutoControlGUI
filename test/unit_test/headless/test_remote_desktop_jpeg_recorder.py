"""Phase 1.3: tests for the no-deps JPEG sequence recorder."""
import json

import pytest

from je_auto_control.utils.remote_desktop.jpeg_recorder import (
    JpegSequenceRecorder, load_manifest,
)


def test_records_three_frames(tmp_path):
    rec = JpegSequenceRecorder(str(tmp_path / "rec"))
    rec.start()
    for i in range(3):
        rec.record_frame(f"jpeg-{i}".encode("ascii"))
    manifest_path = rec.stop()
    assert manifest_path.exists()
    manifest = load_manifest(manifest_path)
    assert manifest["frame_count"] == 3
    assert len(manifest["entries"]) == 3
    for entry in manifest["entries"]:
        assert "filename" in entry and "timestamp" in entry and "size" in entry
        target = manifest_path.parent / entry["filename"]
        assert target.exists()
        assert target.stat().st_size == entry["size"]


def test_record_frame_ignored_before_start(tmp_path):
    rec = JpegSequenceRecorder(str(tmp_path / "rec"))
    rec.record_frame(b"jpeg")
    assert rec.frame_count == 0


def test_record_frame_ignored_after_stop(tmp_path):
    rec = JpegSequenceRecorder(str(tmp_path / "rec"))
    rec.start()
    rec.record_frame(b"first")
    rec.stop()
    rec.record_frame(b"second")
    assert rec.frame_count == 1


def test_stop_is_idempotent(tmp_path):
    rec = JpegSequenceRecorder(str(tmp_path / "rec"))
    rec.start()
    rec.record_frame(b"frame")
    p1 = rec.stop()
    p2 = rec.stop()
    assert p1 == p2 == rec.manifest_path


def test_start_twice_raises(tmp_path):
    rec = JpegSequenceRecorder(str(tmp_path / "rec"))
    rec.start()
    with pytest.raises(RuntimeError):
        rec.start()


def test_record_frame_with_non_bytes_payload(tmp_path):
    """NOSONAR python:S5655  # reason: intentional bad-type negative test."""
    rec = JpegSequenceRecorder(str(tmp_path / "rec"))
    rec.start()
    rec.record_frame("not-bytes")  # type: ignore[arg-type]
    rec.record_frame(None)  # type: ignore[arg-type]
    assert rec.frame_count == 0


def test_manifest_round_trip(tmp_path):
    rec = JpegSequenceRecorder(str(tmp_path / "rec"))
    rec.start()
    rec.record_frame(b"jpeg-data-1")
    rec.record_frame(b"jpeg-data-2")
    path = rec.stop()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw.keys()) == {
        "started_at", "stopped_at", "frame_count", "entries",
    }
    assert raw["entries"][0]["filename"].endswith(".jpg")
