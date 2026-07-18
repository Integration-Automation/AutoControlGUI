"""Round-3 platform regression test: scroll cursor-query guard.

Headless — the backend ``mouse`` object and the cursor helpers are all
monkeypatched, so nothing touches real input or the screen.

Covers audit finding #5: ``mouse_scroll(value, x, y)`` with BOTH
coordinates supplied must NOT query the cursor position (which raises
``NotImplementedError`` on Wayland); it should only be queried to fill in
a coordinate that was actually omitted.
"""
import je_auto_control  # noqa: F401  # load the facade under the real platform first
from je_auto_control.wrapper import auto_control_mouse as acm


class _FakeMouse:
    """Records scroll calls; never touches real input."""

    def __init__(self):
        self.scroll_calls = 0

    def scroll(self, *_args, **_kwargs):
        self.scroll_calls += 1


def _install_common(monkeypatch, get_position):
    """Wire the module globals to fakes and return a call counter dict."""
    calls = {"set_pos": 0}
    fake_mouse = _FakeMouse()
    monkeypatch.setattr(acm, "get_mouse_position", get_position)
    monkeypatch.setattr(acm, "screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(acm, "mouse", fake_mouse)
    monkeypatch.setattr(acm, "special_mouse_keys_table", {}, raising=False)

    def _set_pos(x, y):
        calls["set_pos"] += 1
        return x, y

    monkeypatch.setattr(acm, "set_mouse_position", _set_pos)
    calls["mouse"] = fake_mouse
    return calls


def test_finding5_both_coords_do_not_query_cursor(monkeypatch):
    """With x and y both given, the cursor must never be queried."""
    queried = {"count": 0}

    def _must_not_query():
        queried["count"] += 1
        raise RuntimeError("cursor query must not happen when both coords given")

    calls = _install_common(monkeypatch, _must_not_query)

    # Before the fix this raised RuntimeError (cursor queried unconditionally).
    acm.mouse_scroll(5, x=100, y=200)

    assert queried["count"] == 0
    assert calls["set_pos"] == 1
    assert calls["mouse"].scroll_calls == 1


def test_finding5_missing_coord_still_queries_cursor(monkeypatch):
    """When a coordinate is omitted the cursor IS queried to fill it in."""
    queried = {"count": 0}

    def _query():
        queried["count"] += 1
        return (7, 8)

    calls = _install_common(monkeypatch, _query)

    acm.mouse_scroll(5, x=None, y=200)

    assert queried["count"] == 1
    assert calls["set_pos"] == 1
    assert calls["mouse"].scroll_calls == 1
