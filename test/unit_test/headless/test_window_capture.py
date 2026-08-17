"""Tests for window capture + layout save/restore (injected, no real windows)."""
import json

import pytest

from je_auto_control.utils.window_capture import (
    capture_window, restore_window_layout, save_window_layout, snap_window,
)


def test_capture_window_uses_geometry_and_capture(tmp_path):
    captured = {}
    out = capture_window(
        "Calculator", str(tmp_path / "win.png"),
        geometry=lambda title: (10, 20, 300, 200),
        capture=lambda path, rect: captured.update(path=path, rect=rect),
    )
    assert out == str(tmp_path / "win.png")
    assert captured["rect"] == (10, 20, 300, 200)


def test_capture_window_returns_none_when_not_found(tmp_path):
    out = capture_window(
        "Nope", str(tmp_path / "x.png"),
        geometry=lambda title: None,
        capture=lambda path, rect: None,
    )
    assert out is None


def test_save_window_layout_collects_and_persists(tmp_path):
    rects = {"A": (0, 0, 100, 50), "B": (10, 10, 200, 100)}
    layout = save_window_layout(
        str(tmp_path / "layout.json"),
        lister=lambda: [(1, "A"), (2, "B")],
        geometry=lambda title: rects[title],
    )
    assert len(layout) == 2
    assert layout[0] == {"title": "A", "x": 0, "y": 0,
                         "width": 100, "height": 50}
    saved = json.loads((tmp_path / "layout.json").read_text(encoding="utf-8"))
    assert saved == layout


def test_save_window_layout_skips_windows_without_geometry():
    layout = save_window_layout(
        lister=lambda: [(1, "A"), (2, "B")],
        geometry=lambda title: (0, 0, 10, 10) if title == "A" else None,
    )
    assert [entry["title"] for entry in layout] == ["A"]


def test_restore_window_layout_moves_each_window():
    moved = []

    def mover(title, x, y, width, height):
        moved.append((title, x, y, width, height))
        return True

    count = restore_window_layout(
        [{"title": "A", "x": 1, "y": 2, "width": 3, "height": 4},
         {"title": "B", "x": 5, "y": 6, "width": 7, "height": 8}],
        mover=mover,
    )
    assert count == 2
    assert moved[0] == ("A", 1, 2, 3, 4)


def test_restore_window_layout_reads_from_file(tmp_path):
    path = tmp_path / "l.json"
    path.write_text(
        json.dumps([{"title": "A", "x": 1, "y": 2, "width": 3, "height": 4}]),
        encoding="utf-8",
    )
    assert restore_window_layout(str(path), mover=lambda *a: True) == 1


def test_snap_window_left_half():
    moved = []

    def mover(title, x, y, width, height):
        moved.append((title, x, y, width, height))
        return True

    assert snap_window("Editor", "left", screen_size=lambda: (1000, 800),
                       mover=mover) is True
    assert moved == [("Editor", 0, 0, 500, 800)]


def test_snap_window_right_half():
    rects = []

    def mover(_title, x, y, w, h):
        rects.append((x, y, w, h))
        return 1

    snap_window("E", "right", screen_size=lambda: (1000, 800), mover=mover)
    assert rects == [(500, 0, 500, 800)]


def test_snap_window_max_and_quarter():
    rects = []

    def mover(title, x, y, width, height):
        rects.append((x, y, width, height))
        return True

    snap_window("E", "max", screen_size=lambda: (1000, 800), mover=mover)
    snap_window("E", "bottom-right", screen_size=lambda: (1000, 800),
                mover=mover)
    assert rects == [(0, 0, 1000, 800), (500, 400, 500, 400)]


def test_snap_window_unknown_position_raises():
    with pytest.raises(ValueError):
        snap_window("E", "diagonal", screen_size=lambda: (1000, 800),
                    mover=lambda *a: True)


def test_default_lister_only_offers_windows_restore_can_address(monkeypatch):
    """Saving an untitled window is a promise the restore side cannot keep.

    ``restore_window_layout`` finds a window by title and skips blank ones, so
    an untitled entry inflates the saved count without ever being restored —
    on a real desktop that was 28 saved against 15 restorable.
    """
    from je_auto_control.utils.window_capture import window_capture as wc

    seen = {}

    def _fake_list_windows(titled_only=False):
        seen["titled_only"] = titled_only
        return [(1, "Editor"), (2, "   "), (3, "")]

    import je_auto_control.wrapper.auto_control_window as window_api
    monkeypatch.setattr(window_api, "list_windows", _fake_list_windows)
    assert wc._default_lister() == [(1, "Editor"), (2, "   "), (3, "")]
    assert seen["titled_only"] is True


def test_saved_entries_are_all_restorable():
    """Round-trip: every entry save produces must survive restore."""
    layout = save_window_layout(
        lister=lambda: [(1, "Editor"), (2, "Browser")],
        geometry=lambda title: (0, 0, 100, 100),
    )
    moved = []
    restored = restore_window_layout(
        layout, mover=lambda title, *rect: moved.append(title) or True)
    assert restored == len(layout) == 2
    assert moved == ["Editor", "Browser"]
