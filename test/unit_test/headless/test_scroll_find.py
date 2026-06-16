"""Tests for scroll_until_visible (injectable locator + scroller)."""
from je_auto_control.utils.scroll_find import scroll_until_visible


def test_found_after_scrolling():
    state = {"n": 0}

    def locate(target):
        state["n"] += 1
        return (10, 20) if state["n"] >= 3 else None  # visible on 3rd check

    scrolls = []
    result = scroll_until_visible(
        "btn.png", max_scrolls=10,
        locator=locate, scroller=lambda d, a: scrolls.append((d, a)),
    )
    assert result["found"] is True
    assert result["coords"] == [10, 20]
    assert result["scrolls"] == 2  # two scrolls before it appeared
    assert len(scrolls) == 2


def test_not_found_within_budget():
    scrolls = []
    result = scroll_until_visible(
        "x.png", max_scrolls=3,
        locator=lambda t: None, scroller=lambda d, a: scrolls.append(a),
    )
    assert result["found"] is False
    assert result["scrolls"] == 3
    assert len(scrolls) == 3


def test_found_immediately_does_not_scroll():
    scrolls = []
    result = scroll_until_visible(
        "x.png", locator=lambda t: (1, 2),
        scroller=lambda d, a: scrolls.append(a),
    )
    assert result["found"] is True
    assert result["scrolls"] == 0
    assert scrolls == []


def test_direction_passed_to_scroller():
    seen = []
    scroll_until_visible(
        "x", direction="up", max_scrolls=1,
        locator=lambda t: None, scroller=lambda d, a: seen.append(d),
    )
    assert seen == ["up"]
