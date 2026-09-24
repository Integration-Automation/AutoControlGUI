"""Locator / geometry defects from the 2026-09-24 audit (no real input or screen).

A sideways scroll-find scrolled vertically; two elements could inherit one
"stable" id; a remapped
point could land just off the target monitor; a grid point could fall outside
the cell returned for it; window grid cells left 1 px gaps; the A/B stats file
lost counts written by another store and was overwritten when damaged; one
malformed strategy ended the whole A/B run.
"""
import json

import pytest

from je_auto_control.utils.ab_locator import runner
from je_auto_control.utils.ab_locator.store import ABStore
from je_auto_control.utils.element_diff.element_diff import assign_stable_ids
from je_auto_control.utils.monitor_layout.monitor_layout import Monitor, remap_point
from je_auto_control.utils.scroll_find import scroll_find
from je_auto_control.utils.screen_grid.screen_grid import cell_for_point, grid_cells
from je_auto_control.utils.window_layout.window_layout import grid_rects
from je_auto_control.wrapper import auto_control_mouse


def _box(x, y, w, h, **extra):
    return dict(x=x, y=y, width=w, height=h, **extra)


def test_sideways_scrolling_is_not_sent_as_vertical(monkeypatch):
    calls = []
    monkeypatch.setattr(auto_control_mouse, "mouse_scroll",
                        lambda value, scroll_direction="scroll_down": calls.append(
                            (value, scroll_direction)))
    monkeypatch.setattr(auto_control_mouse, "special_mouse_keys_table", {})
    with pytest.raises(ValueError, match="horizontal"):
        scroll_find._default_scroller("right", 3)
    monkeypatch.setattr(auto_control_mouse, "special_mouse_keys_table",
                        {"scroll_right": 7, "scroll_up": 4})
    scroll_find._default_scroller("right", 3)
    scroll_find._default_scroller("down", 3)
    assert calls == [(3, "scroll_right"), (-3, "scroll_up")]


def test_stable_ids_are_never_shared():
    prior = [_box(0, 0, 100, 100, id=0)]
    tagged = assign_stable_ids([_box(0, 0, 100, 100), _box(0, 0, 100, 60)], prior)
    assert sorted(item["id"] for item in tagged) == [0, 1]


def test_a_remapped_point_stays_on_the_target_monitor():
    src = Monitor(index=0, x=0, y=0, width=1000, height=1000)
    dst = Monitor(index=1, x=1000, y=0, width=100, height=100)
    assert remap_point(src, dst, 999, 999) == (99, 99)


def test_the_cell_for_a_point_contains_it():
    for x in range(10):
        cell = cell_for_point(x, 0, 1, 3, region=(0, 0, 10, 10))
        assert cell.left <= x < cell.right
    cells = grid_cells(1, 3, region=(0, 0, 10, 10))
    assert cell_for_point(3, 0, 1, 3, region=(0, 0, 10, 10)).label == cells[1].label


def test_window_grid_cells_meet_exactly():
    rects = grid_rects((0, 0, 1000, 100), 1, 3)
    edges = [(rect.x, rect.x + rect.width) for rect in rects]
    assert edges == [(0, 333), (333, 667), (667, 1000)]


def test_two_stores_on_one_file_keep_each_others_counts(tmp_path):
    path = tmp_path / "ab.json"
    first, second = ABStore(path), ABStore(path)
    first.record(target_id="t", strategy="s", succeeded=True, elapsed_ms=1)
    second.record(target_id="t", strategy="s", succeeded=True, elapsed_ms=1)
    first.record(target_id="t", strategy="s", succeeded=False, elapsed_ms=1)
    [row] = json.loads(path.read_text(encoding="utf-8"))
    assert (row["successes"], row["failures"]) == (2, 1)


def test_a_damaged_stats_file_is_set_aside_not_overwritten(tmp_path):
    path = tmp_path / "ab.json"
    path.write_text("{not json", encoding="utf-8")
    ABStore(path).record(target_id="t", strategy="s", succeeded=True, elapsed_ms=1)
    assert list(tmp_path.glob("ab.json.corrupt-*"))


def test_a_malformed_strategy_is_a_failed_strategy(monkeypatch, tmp_path):
    def resolve(locator):
        if locator == "bad":
            raise TypeError("template_path is None")
        return (1, 2)

    monkeypatch.setattr(runner, "_resolve_single", resolve)
    outcome = runner.ab_locate(target_id="t", strategies={"a": "good", "b": "bad"},
                               store=ABStore(tmp_path / "ab.json"))
    assert outcome.winner == "a"
    assert outcome.results["b"].succeeded is False
