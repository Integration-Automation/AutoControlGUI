"""Tests for the anchor-based locator (spatial composition)."""
from unittest.mock import patch

import pytest

from je_auto_control.utils.anchor_locator import (
    AnchorLocatorError, AnchorOutcome, Locator, REL_ABOVE, REL_BELOW,
    REL_LEFT_OF, REL_NEAR, REL_RIGHT_OF, a11y_locator, anchor_locate,
    image_locator, ocr_locator, vlm_locator,
)
from je_auto_control.utils.anchor_locator import locator as locator_mod


# === Locator constructors ==================================================

def test_image_locator_normalises_fields():
    loc = image_locator("submit.png", detect_threshold=0.85)
    assert loc.kind == "image"
    assert loc.template_path == "submit.png"
    assert loc.detect_threshold == 0.85


def test_ocr_locator_carries_region():
    loc = ocr_locator("Submit", min_confidence=70, region=[0, 0, 100, 50])
    assert loc.text == "Submit"
    assert loc.region == (0, 0, 100, 50)


def test_vlm_locator_passes_model():
    loc = vlm_locator("green button", model="claude-opus-4-7")
    assert loc.model == "claude-opus-4-7"


def test_a11y_locator_requires_at_least_one_filter():
    with pytest.raises(AnchorLocatorError):
        a11y_locator()


def test_locator_rejects_unknown_kind():
    with pytest.raises(AnchorLocatorError):
        Locator(kind="psychic")


# === Relation normalisation ===============================================

def test_anchor_locate_rejects_unknown_relation(monkeypatch):
    monkeypatch.setattr(locator_mod, "_resolve_single", lambda _l: (0, 0))
    monkeypatch.setattr(locator_mod, "_resolve_candidates", lambda _l: [])
    with pytest.raises(AnchorLocatorError):
        anchor_locate(
            anchor=image_locator("a.png"),
            target=image_locator("b.png"),
            relation="diagonally",
        )


# === Resolution paths =====================================================

def _patch_single(monkeypatch, value):
    monkeypatch.setattr(locator_mod, "_resolve_single", lambda _l: value)


def _patch_candidates(monkeypatch, bboxes):
    monkeypatch.setattr(
        locator_mod, "_resolve_candidates",
        lambda _l: [locator_mod._Bbox(*tup) for tup in bboxes],
    )


def test_anchor_not_found_returns_unmatched_outcome(monkeypatch):
    _patch_single(monkeypatch, None)
    _patch_candidates(monkeypatch, [])
    outcome = anchor_locate(
        anchor=image_locator("a.png"),
        target=image_locator("b.png"),
        relation=REL_NEAR,
    )
    assert isinstance(outcome, AnchorOutcome)
    assert outcome.found is False
    assert outcome.error == "anchor not found"


def test_target_not_found_returns_unmatched_outcome(monkeypatch):
    _patch_single(monkeypatch, (100, 100))
    _patch_candidates(monkeypatch, [])
    outcome = anchor_locate(
        anchor=image_locator("a.png"),
        target=image_locator("b.png"),
        relation=REL_NEAR,
    )
    assert outcome.found is False
    assert outcome.anchor_coords == (100, 100)
    assert outcome.error == "target not found"


def test_near_relation_returns_closest_candidate(monkeypatch):
    _patch_single(monkeypatch, (100, 100))
    _patch_candidates(monkeypatch, [
        (200, 100, 220, 120),  # center (210, 110), distance ~ 110
        (110, 100, 130, 120),  # center (120, 110), distance ~ 22
        (50, 50, 60, 60),       # center (55, 55), distance ~ 67
    ])
    outcome = anchor_locate(
        anchor=image_locator("a.png"),
        target=image_locator("b.png"),
        relation=REL_NEAR,
    )
    assert outcome.found is True
    assert outcome.target_coords == (120, 110)
    assert outcome.candidates_considered == 3


def test_near_relation_respects_max_distance(monkeypatch):
    _patch_single(monkeypatch, (0, 0))
    _patch_candidates(monkeypatch, [
        (1000, 1000, 1020, 1020),
    ])
    outcome = anchor_locate(
        anchor=image_locator("a.png"),
        target=image_locator("b.png"),
        relation=REL_NEAR, max_distance_px=100.0,
    )
    assert outcome.found is False


def test_below_relation_filters_candidates_above_anchor(monkeypatch):
    _patch_single(monkeypatch, (100, 100))
    _patch_candidates(monkeypatch, [
        (90, 50, 110, 70),    # center (100, 60) — above anchor
        (90, 150, 110, 170),  # center (100, 160) — below anchor
    ])
    outcome = anchor_locate(
        anchor=ocr_locator("Username"),
        target=image_locator("submit.png"),
        relation=REL_BELOW,
    )
    assert outcome.found is True
    assert outcome.target_coords == (100, 160)


def test_above_relation_filters_correctly(monkeypatch):
    _patch_single(monkeypatch, (100, 100))
    _patch_candidates(monkeypatch, [
        (90, 150, 110, 170),  # below — excluded
        (90, 50, 110, 70),    # above — should win
    ])
    outcome = anchor_locate(
        anchor=ocr_locator("anchor"),
        target=image_locator("target.png"),
        relation=REL_ABOVE,
    )
    assert outcome.target_coords == (100, 60)


def test_left_of_relation_picks_left_candidate(monkeypatch):
    _patch_single(monkeypatch, (100, 100))
    _patch_candidates(monkeypatch, [
        (200, 90, 220, 110),  # right
        (50, 90, 70, 110),    # left
    ])
    outcome = anchor_locate(
        anchor=image_locator("anchor.png"),
        target=image_locator("target.png"),
        relation=REL_LEFT_OF,
    )
    assert outcome.target_coords == (60, 100)


def test_right_of_relation_picks_right_candidate(monkeypatch):
    _patch_single(monkeypatch, (100, 100))
    _patch_candidates(monkeypatch, [
        (200, 90, 220, 110),
        (50, 90, 70, 110),
    ])
    outcome = anchor_locate(
        anchor=image_locator("anchor.png"),
        target=image_locator("target.png"),
        relation=REL_RIGHT_OF,
    )
    assert outcome.target_coords == (210, 100)


def test_no_candidate_matches_relation_reports_failure(monkeypatch):
    _patch_single(monkeypatch, (100, 100))
    _patch_candidates(monkeypatch, [
        (90, 50, 110, 70),  # only candidate is above
    ])
    outcome = anchor_locate(
        anchor=image_locator("anchor.png"),
        target=image_locator("target.png"),
        relation=REL_BELOW,
    )
    assert outcome.found is False
    assert outcome.candidates_considered == 1


# === Backend integration ==================================================

def test_image_candidates_calls_locate_all_image():
    with patch(
        "je_auto_control.wrapper.auto_control_image.locate_all_image",
        return_value=[[10, 10, 30, 30], [50, 50, 70, 70]],
    ) as mocked:
        bboxes = locator_mod._image_candidates(
            image_locator("a.png"),
        )
    mocked.assert_called_once()
    assert len(bboxes) == 2


def test_ocr_candidates_calls_find_text_matches():
    from je_auto_control.utils.ocr.ocr_engine import TextMatch
    with patch(
        "je_auto_control.utils.ocr.ocr_engine.find_text_matches",
        return_value=[TextMatch(text="x", x=10, y=20, width=30,
                                  height=10, confidence=90.0)],
    ) as mocked:
        bboxes = locator_mod._ocr_candidates(ocr_locator("x"))
    mocked.assert_called_once()
    assert bboxes[0].x1 == 10
    assert bboxes[0].x2 == 40


def test_vlm_point_calls_locate_by_description():
    with patch(
        "je_auto_control.utils.vision.vlm_api.locate_by_description",
        return_value=(50, 60),
    ) as mocked:
        point = locator_mod._vlm_point(vlm_locator("green button"))
    mocked.assert_called_once()
    assert point == (50, 60)


# === Outcome serialisation ================================================

def test_outcome_to_dict_uses_lists_for_coords():
    outcome = AnchorOutcome(
        found=True, target_coords=(10, 20), anchor_coords=(30, 40),
        distance_px=5.5, relation=REL_NEAR,
        target_kind="image", anchor_kind="ocr",
    )
    data = outcome.to_dict()
    assert data["target_coords"] == [10, 20]
    assert data["anchor_coords"] == [30, 40]


# === Executor / MCP / facade ==============================================

def test_executor_registers_anchor_commands():
    from je_auto_control.utils.executor.action_executor import executor
    assert {"AC_anchor_locate", "AC_anchor_click"} <= executor.known_commands()


def test_mcp_factory_registers_anchor_tools():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert {"ac_anchor_locate", "ac_anchor_click"} <= names


def test_facade_exports_anchor_api():
    import je_auto_control as ac
    for name in ("anchor_locate", "image_locator", "ocr_locator",
                  "vlm_locator", "a11y_locator", "AnchorOutcome",
                  "AnchorLocator"):
        assert hasattr(ac, name)
