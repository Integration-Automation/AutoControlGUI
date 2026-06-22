"""Headless tests for anchor ordinal / locate-all. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.anchor_locator import (
    anchor_locate, anchor_locate_all, image_locator,
)
from je_auto_control.utils.anchor_locator import locator as locator_mod


def _patch(monkeypatch, anchor_point, bboxes):
    monkeypatch.setattr(locator_mod, "_resolve_single", lambda _l: anchor_point)
    monkeypatch.setattr(
        locator_mod, "_resolve_candidates",
        lambda _l: [locator_mod._Bbox(*tup) for tup in bboxes])


_ANCHOR = image_locator("a.png")
_TARGET = image_locator("b.png")
# three targets below the anchor at (0, 0), at increasing distance
_BELOW = [(0, 100, 10, 110), (0, 200, 10, 210), (0, 300, 10, 310)]


def test_ordinal_selects_nth_nearest(monkeypatch):
    _patch(monkeypatch, (0, 0), _BELOW)
    first = anchor_locate(anchor=_ANCHOR, target=_TARGET, relation="below")
    assert first.found and first.target_coords == (5, 105)        # nearest
    second = anchor_locate(anchor=_ANCHOR, target=_TARGET, relation="below",
                           ordinal=2)
    assert second.found and second.target_coords == (5, 205)
    third = anchor_locate(anchor=_ANCHOR, target=_TARGET, relation="below",
                          ordinal=3)
    assert third.found and third.target_coords == (5, 305)


def test_ordinal_out_of_range_not_found(monkeypatch):
    _patch(monkeypatch, (0, 0), _BELOW)
    outcome = anchor_locate(anchor=_ANCHOR, target=_TARGET, relation="below",
                            ordinal=9)
    assert outcome.found is False and "ordinal" in outcome.error


def test_locate_all_returns_sorted(monkeypatch):
    _patch(monkeypatch, (0, 0), _BELOW)
    results = anchor_locate_all(anchor=_ANCHOR, target=_TARGET, relation="below")
    assert [r.target_coords for r in results] == [(5, 105), (5, 205), (5, 305)]
    assert all(r.found for r in results)


def test_locate_all_empty_when_anchor_missing(monkeypatch):
    _patch(monkeypatch, None, _BELOW)
    assert anchor_locate_all(anchor=_ANCHOR, target=_TARGET) == []


def test_relation_filters_before_ordinal(monkeypatch):
    # one above, two below -> "below" ordinal=2 is the farther below one
    _patch(monkeypatch, (0, 150),
           [(0, 50, 10, 60), (0, 200, 10, 210), (0, 300, 10, 310)])
    out = anchor_locate(anchor=_ANCHOR, target=_TARGET, relation="below",
                        ordinal=2)
    assert out.target_coords == (5, 305)


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_anchor_locate_all" in set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_anchor_locate_all" in names


def test_facade_exports():
    assert hasattr(ac, "anchor_locate_all")
    assert "anchor_locate_all" in ac.__all__
