"""Phase 6.4 + 6.7: semantic recording enrichment and replay relocation."""
from je_auto_control.utils.semantic_recording import (
    AnchorLocator, AnchorResolver, enrich_action, enrich_recording,
    relocate_action, relocate_recording,
)


# --- enrichment --------------------------------------------------------

def test_enrich_action_adds_anchor_for_click():
    """A backend that always returns the same anchor must be applied."""

    def backend(x, y):
        return {"kind": "a11y", "role": "Button", "name": "Login"}

    resolver = AnchorResolver(backend=backend)
    enriched = enrich_action(
        {"action": "mouse_press", "x": 100, "y": 50, "button": "left"},
        resolver=resolver,
    )
    assert enriched["anchor"] == {
        "kind": "a11y", "role": "Button", "name": "Login",
    }
    # Unrelated fields preserved.
    assert enriched["button"] == "left"


def test_enrich_action_passes_non_click_through():
    """A type action has no x/y to anchor — output is unchanged."""
    action = {"action": "type", "text": "hello"}
    assert enrich_action(action) == action


def test_enrich_skips_actions_missing_coordinates():
    """mouse_press without x/y just passes through."""
    action = {"action": "mouse_press", "button": "left"}
    assert enrich_action(action) == action


def test_enrich_recording_returns_new_list():
    """Original list / dicts are not mutated."""
    raw = [
        {"action": "mouse_press", "x": 1, "y": 2, "button": "left"},
        {"action": "type", "text": "x"},
    ]
    resolver = AnchorResolver(backend=lambda x, y: {"role": "B"})
    enriched = enrich_recording(raw, resolver)
    assert "anchor" not in raw[0]  # original untouched
    assert enriched[0]["anchor"] == {"role": "B"}
    assert enriched[1] == raw[1]


def test_resolver_swallows_backend_errors():
    """A backend that raises returns no anchor — replay falls back."""

    def boom(x, y):
        raise RuntimeError("backend down")

    resolver = AnchorResolver(backend=boom)
    enriched = enrich_action(
        {"action": "mouse_press", "x": 1, "y": 2, "button": "left"},
        resolver=resolver,
    )
    assert "anchor" not in enriched


# --- replay relocation -------------------------------------------------

def test_relocate_rewrites_xy_from_anchor():
    """Locator returning a fresh position is applied to the action."""

    def locator(anchor):
        return (500, 600)

    out = relocate_action(
        {"action": "mouse_press", "x": 10, "y": 20,
         "anchor": {"role": "Button", "name": "Save"}, "button": "left"},
        locator=AnchorLocator(backend=locator),
    )
    assert out["x"] == 500
    assert out["y"] == 600
    assert out["relocated"] is True


def test_relocate_keeps_xy_when_anchor_missing():
    """No anchor → no rewrite, no `relocated` flag."""
    raw = {"action": "mouse_press", "x": 10, "y": 20, "button": "left"}
    out = relocate_action(raw)
    assert out["x"] == 10
    assert out["y"] == 20
    assert "relocated" not in out


def test_relocate_keeps_xy_when_locator_fails():
    """Locator returning None → original x/y stays, relocated=False."""
    out = relocate_action(
        {"action": "mouse_press", "x": 10, "y": 20,
         "anchor": {"role": "Button", "name": "MovedAway"}, "button": "left"},
        locator=AnchorLocator(backend=lambda anchor: None),
    )
    assert out["x"] == 10
    assert out["y"] == 20
    assert out["relocated"] is False


def test_relocate_recording_round_trip():
    """End-to-end: enrich then relocate. Coords should change if backend moves."""
    raw = [{"action": "mouse_press", "x": 10, "y": 20, "button": "left"}]
    enriched = enrich_recording(
        raw, AnchorResolver(backend=lambda x, y:
                            {"kind": "a11y", "role": "B", "name": "X"}),
    )
    moved = relocate_recording(
        enriched, AnchorLocator(backend=lambda anchor: (777, 888)),
    )
    assert moved[0]["x"] == 777
    assert moved[0]["y"] == 888
    assert moved[0]["relocated"] is True


def test_relocate_ignores_non_click_actions():
    """Typing or key actions are untouched even with an anchor."""
    raw = {"action": "type", "text": "hi", "anchor": {"role": "X"}}
    assert relocate_action(raw) == raw


def test_locator_swallows_backend_errors():
    """Backend raising returns None → relocate falls back gracefully."""

    def boom(anchor):
        raise OSError("locate failed")

    out = relocate_action(
        {"action": "mouse_press", "x": 1, "y": 2,
         "anchor": {"role": "X"}, "button": "left"},
        locator=AnchorLocator(backend=boom),
    )
    assert out["x"] == 1 and out["y"] == 2
    assert out["relocated"] is False
