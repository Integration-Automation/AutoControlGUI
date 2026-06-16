"""Tests for move_to_trash (recoverable deletion; injected backend)."""
import pytest

from je_auto_control.utils.trash import move_to_trash


def test_move_to_trash_calls_backend_with_resolved_path(tmp_path):
    target = tmp_path / "doomed.txt"
    target.write_text("bye", encoding="utf-8")
    seen = []
    assert move_to_trash(target, backend=seen.append) is True
    assert seen == [str(target.resolve())]


def test_move_to_trash_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        move_to_trash(tmp_path / "nope.txt", backend=lambda p: None)


def test_move_to_trash_does_not_delete_when_backend_used(tmp_path):
    target = tmp_path / "keep.txt"
    target.write_text("still here", encoding="utf-8")
    # A no-op backend stands in for the recycle bin; the file is untouched.
    move_to_trash(target, backend=lambda p: None)
    assert target.exists()
