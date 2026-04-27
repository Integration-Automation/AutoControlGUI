"""Tests for the AuditLogTab event_type dropdown helper (round 45).

The actual ``AuditLogTab`` widget needs Qt; we just exercise the pure
helper that builds the dropdown values, which is the place a regression
would actually surface.
"""
import pytest

# AuditLogTab transitively imports PySide6 (and gui/__init__.py pulls
# webrtc_panel → aiortc). Only the helper function in the same module
# is pure; gate the whole module on Qt + the webrtc extra to keep the
# import chain happy.
pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("av")
pytest.importorskip("aiortc")

from je_auto_control.gui.audit_log_tab import (  # noqa: E402
    _ALL_SENTINEL, _PINNED_PRESETS, build_event_type_choices,
)


def test_pinned_presets_appear_when_log_is_empty():
    choices = build_event_type_choices([])
    assert choices[0] == _ALL_SENTINEL
    for preset in _PINNED_PRESETS:
        assert preset in choices


def test_observed_types_appear_after_presets():
    choices = build_event_type_choices(["custom_event_a", "custom_event_b"])
    assert "custom_event_a" in choices
    assert "custom_event_b" in choices
    assert choices.index("custom_event_a") > choices.index(_PINNED_PRESETS[-1])


def test_duplicate_event_types_are_deduped():
    choices = build_event_type_choices([
        "custom", "custom", "custom",
    ])
    assert choices.count("custom") == 1


def test_observed_type_that_overlaps_a_preset_does_not_duplicate():
    choices = build_event_type_choices(["usb_open_allowed"])
    assert choices.count("usb_open_allowed") == 1


def test_empty_event_type_is_dropped():
    choices = build_event_type_choices(["", "real_event", ""])
    assert "" not in choices
    assert "real_event" in choices


def test_all_sentinel_is_first():
    choices = build_event_type_choices(["whatever"])
    assert choices[0] == _ALL_SENTINEL
