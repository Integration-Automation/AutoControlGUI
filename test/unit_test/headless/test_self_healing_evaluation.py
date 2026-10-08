"""Self-healing measurement: labelled evaluation, heal-log schema, verified actions.

Everything here runs on arrays built in the test and on fakes for the two
locator strategies; nothing captures the screen or moves the pointer.
"""
import json

import numpy as np
import pytest

from je_auto_control.utils.self_healing import (
    HealEvent, HealEventLog, self_heal_click, self_heal_locate,
)
from je_auto_control.utils.self_healing import locator as locator_mod
from je_auto_control.utils.self_healing.evaluation import (
    EvaluationSample, HealingEvaluationError, Ratio, check_thresholds,
    evaluate_locators, format_comparison,
)
from je_auto_control.utils.self_healing.heal_log import HEAL_EVENT_SCHEMA_VERSION
from je_auto_control.utils.self_healing.locator import heal_context


def _frame(seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 255, (40, 60), dtype=np.uint8)


def _always(point):
    return lambda request: point


def _never(request):
    return None


# --- evaluate_locators ---------------------------------------------------


def test_unlabelled_is_unknown():
    samples = [
        EvaluationSample("labelled", _frame(1), expected_box=(0, 0, 10, 10)),
        EvaluationSample("unlabelled", _frame(2)),
    ]
    report = evaluate_locators(samples, {"v1": _always((5, 5))}).report("v1")
    assert report.unknown == 1
    # The unlabelled hit is counted as located, and as nothing else.
    assert report.located == 2
    assert report.correct == 1
    assert report.accuracy == Ratio(1, 1)
    assert report.hit_rate == Ratio(2, 2)


def test_false_positive_is_not_recovery():
    samples = [
        EvaluationSample("a", _frame(1), expected_box=(0, 0, 10, 10)),
        EvaluationSample("b", _frame(2), expected_box=(20, 20, 30, 30)),
    ]
    # v2 "finds" both, but the second hit is nowhere near the target.
    comparison = evaluate_locators(
        samples, {"v1": _never, "v2": _always((5, 5))})
    report = comparison.report("v2")
    assert report.correct == 1 and report.false_positive == 1
    assert report.located == 2
    assert report.recovery_rate == Ratio(1, 2)
    assert comparison.report("v1").miss == 2
    assert [row.sample_id for row in comparison.failures("v2")] == ["b"]


def test_hit_on_an_expected_miss_is_a_false_positive():
    samples = [EvaluationSample("gone", _frame(), expect_miss=True)]
    comparison = evaluate_locators(
        samples, {"strict": _never, "loose": _always((1, 1))})
    assert comparison.report("strict").true_negative == 1
    assert comparison.report("strict").accuracy == Ratio(1, 1)
    assert comparison.report("loose").false_positive == 1
    assert comparison.report("loose").accuracy == Ratio(0, 1)
    # A sample that expects a miss can never be "recovered".
    assert comparison.report("loose").recovery_rate == Ratio(0, 0)
    assert comparison.report("loose").recovery_rate.value is None


def test_same_frame_versions_are_comparable():
    seen = {}

    def record(name):
        def strategy(request):
            seen[name] = request
            return None
        return strategy

    frame = _frame(7)
    sample = EvaluationSample("s", frame, expected_box=(0, 0, 5, 5),
                              origin=(-1920, -200), scale=1.5)
    comparison = evaluate_locators([sample], {"a": record("a"), "b": record("b")})
    assert seen["a"].frame is frame and seen["b"].frame is frame
    assert seen["a"] is seen["b"]
    assert seen["a"].origin == (-1920, -200) and seen["a"].scale == 1.5
    hashes = {row.frame_hash for row in comparison.results}
    assert len(hashes) == 1 and None not in hashes


def test_region_passed_to_both_strategies():
    regions = {}

    def record(name):
        def strategy(request):
            regions[name] = request.region
            return None
        return strategy

    sample = EvaluationSample("s", _frame(), expected_box=(12, 12, 20, 20),
                              region=(10, 10, 50, 30))
    evaluate_locators([sample], {"image": record("image"), "vlm": record("vlm")})
    image_region, vlm_region = regions["image"], regions["vlm"]
    assert image_region == vlm_region
    assert image_region == (10, 10, 50, 30)


def test_a_strategy_that_edits_the_frame_is_refused():
    def vandal(request):
        request.frame[0, 0] ^= 0xFF
        return None

    sample = EvaluationSample("s", _frame(), expected_box=(0, 0, 5, 5))
    with pytest.raises(HealingEvaluationError, match="modified the frame"):
        evaluate_locators([sample], {"vandal": vandal, "later": _never})


def test_negative_origin_box_is_judged_in_screen_coordinates():
    sample = EvaluationSample("left-monitor", _frame(),
                              expected_box=(-1900, -180, -1880, -160),
                              origin=(-1920, -200))
    comparison = evaluate_locators(
        [sample], {"right": _always((-1890, -170)), "frame-local": _always((30, 30))})
    assert comparison.report("right").correct == 1
    assert comparison.report("frame-local").false_positive == 1


def test_strategy_error_is_its_own_bucket():
    def broken(request):
        raise RuntimeError("backend down")

    samples = [EvaluationSample("s", _frame(), expect_miss=True)]
    report = evaluate_locators(samples, {"broken": broken}).report("broken")
    # Raising on a sample that expects a miss is not a correct rejection.
    assert report.error == 1 and report.true_negative == 0
    assert report.accuracy == Ratio(0, 1)


def test_latency_percentiles_and_counts_are_reported():
    ticks = iter(range(0, 1000))
    samples = [EvaluationSample(f"s{i}", _frame(i), expected_box=(0, 0, 9, 9))
               for i in range(4)]
    comparison = evaluate_locators(
        samples, {"v1": _always((1, 1))}, clock=lambda: next(ticks) / 1000.0)
    report = comparison.report("v1")
    assert report.p50_ms == pytest.approx(1.0)
    assert report.p95_ms == pytest.approx(1.0)
    payload = json.loads(json.dumps(comparison.to_dict()))
    version = payload["versions"]["v1"]
    assert version["accuracy"] == {"numerator": 4, "denominator": 4, "value": 1.0}
    assert version["false_positive_rate"]["denominator"] == 4
    assert payload["baseline"] == "v1"
    assert "4/4" in format_comparison(comparison)


def test_empty_ratio_has_no_value_rather_than_a_perfect_one():
    report = evaluate_locators(
        [EvaluationSample("u", _frame())], {"v1": _never}).report("v1")
    assert report.accuracy.to_dict() == {
        "numerator": 0, "denominator": 0, "value": None}


def test_invalid_inputs_are_rejected():
    sample = EvaluationSample("s", _frame(), expected_box=(0, 0, 5, 5))
    with pytest.raises(HealingEvaluationError):
        evaluate_locators([sample], {})
    with pytest.raises(HealingEvaluationError, match="duplicate"):
        evaluate_locators([sample, sample], {"v1": _never})
    with pytest.raises(HealingEvaluationError, match="expect_miss"):
        EvaluationSample("x", _frame(), expected_box=(0, 0, 5, 5), expect_miss=True)
    with pytest.raises(HealingEvaluationError, match="scale"):
        EvaluationSample("x", _frame(), scale=0)


def test_thresholds_report_each_violation():
    samples = [EvaluationSample("a", _frame(), expected_box=(0, 0, 10, 10)),
               EvaluationSample("b", _frame(1), expect_miss=True)]
    comparison = evaluate_locators(samples, {"v1": _always((5, 5))})
    assert check_thresholds(comparison, {"v1": {"min_correct": 1}}) == []
    violations = check_thresholds(
        comparison, {"v1": {"max_false_positive": 0, "min_accuracy": 0.9},
                     "missing": {"min_correct": 1}})
    assert len(violations) == 3


# --- the live locator: one region for both strategies ----------------------


@pytest.fixture
def temp_log(tmp_path):
    return HealEventLog(path=tmp_path / "events.jsonl")


def test_live_locate_gives_the_region_to_image_and_vlm(monkeypatch, temp_log):
    seen = {}

    def fake_find_image(image, detect_threshold=1.0, draw_image=False,
                        all_screens=True, screen_region=None):
        seen["image"] = screen_region
        return [False, []]

    def fake_vlm(description, screen_region, model):
        seen["vlm"] = screen_region
        return None, "no match"

    from je_auto_control.utils.cv2_utils import template_detection
    monkeypatch.setattr(template_detection, "find_image", fake_find_image)
    monkeypatch.setattr(locator_mod, "_try_vlm", fake_vlm)
    outcome = self_heal_locate(template_path="t.png", description="the button",
                               screen_region=[-100, 20, 300, 220], log=temp_log)
    assert outcome.found is False
    # Two corners for the VLM, (x, y, width, height) for the matcher: one box.
    assert seen["vlm"] == [-100, 20, 300, 220]
    assert seen["image"] == (-100, 20, 400, 200)
    assert temp_log.list_events()[0].screen_region == [-100, 20, 300, 220]


def test_live_locate_rejects_a_region_without_area(temp_log):
    with pytest.raises(ValueError):
        self_heal_locate(template_path="t.png", screen_region=[10, 10, 10, 50],
                         log=temp_log)


# --- located vs verified -------------------------------------------------


def _patch_hit(monkeypatch, clicks):
    monkeypatch.setattr(locator_mod, "_try_image", lambda path, threshold: ((7, 9), None))
    monkeypatch.setattr(locator_mod, "_click_at",
                        lambda coords, keycode: clicks.append(coords))


def test_click_without_a_check_is_located_but_not_verified(monkeypatch, temp_log):
    clicks = []
    _patch_hit(monkeypatch, clicks)
    outcome = self_heal_click(template_path="t.png", log=temp_log)
    assert outcome.found is True and outcome.action == "click"
    assert outcome.action_verified is None
    event = temp_log.list_events()[0]
    assert event.action == "click" and event.action_verified is None
    assert clicks == [(7, 9)]


@pytest.mark.parametrize("verdict", [True, False])
def test_click_records_what_the_check_said(monkeypatch, temp_log, verdict):
    _patch_hit(monkeypatch, [])
    outcome = self_heal_click(template_path="t.png", log=temp_log,
                              verify=lambda result: verdict)
    assert outcome.found is True
    assert outcome.action_verified is verdict
    events = temp_log.list_events()
    assert len(events) == 1 and events[0].action_verified is verdict


def test_a_failed_click_is_still_logged_and_never_verified(monkeypatch, temp_log):
    monkeypatch.setattr(locator_mod, "_try_image", lambda path, threshold: ((1, 2), None))

    def boom(coords, keycode):
        raise OSError("pointer unavailable")

    monkeypatch.setattr(locator_mod, "_click_at", boom)
    with pytest.raises(OSError):
        self_heal_click(template_path="t.png", log=temp_log, verify=lambda result: True)
    event = temp_log.list_events()[0]
    assert event.action == "click" and event.action_verified is None


def test_bare_locate_has_no_action(monkeypatch, temp_log):
    _patch_hit(monkeypatch, [])
    outcome = self_heal_locate(template_path="t.png", log=temp_log)
    assert outcome.action is None and outcome.action_verified is None


# --- heal log schema -----------------------------------------------------


def test_old_format_lines_still_load(tmp_path):
    path = tmp_path / "events.jsonl"
    old = {"timestamp": "2026-05-01T00:00:00+00:00", "method": "image",
           "coordinates": [1, 2], "duration_ms": 3.5, "template_path": "a.png",
           "description": None, "image_error": None, "vlm_error": None}
    newer = dict(old, schema_version=99, locator_version="v9",
                 a_field_from_the_future={"x": 1})
    path.write_text(json.dumps(old) + "\n" + json.dumps(newer) + "\n[1, 2]\n",
                    encoding="utf-8")
    events = HealEventLog(path=path).list_events()
    assert len(events) == 2
    assert events[0].schema_version is None and events[0].locator_version is None
    assert events[0].coordinates == [1, 2]
    assert events[1].locator_version == "v9"


def test_context_is_stamped_on_events(monkeypatch, temp_log):
    _patch_hit(monkeypatch, [])
    with heal_context(run_id="run-1", locator_id="submit", locator_version="v2"):
        self_heal_locate(template_path="t.png", model="m-1", log=temp_log)
    self_heal_locate(template_path="t.png", log=temp_log)
    inside, outside = temp_log.list_events()
    assert (inside.run_id, inside.locator_id, inside.locator_version) == (
        "run-1", "submit", "v2")
    assert inside.model == "m-1"
    assert inside.schema_version == HEAL_EVENT_SCHEMA_VERSION
    assert inside.image_ms is not None
    assert outside.run_id is None and outside.locator_version is None


def test_unknown_context_key_is_rejected():
    with pytest.raises(ValueError):
        with heal_context(colour="blue"):
            pass


def test_event_round_trips_through_the_log(temp_log):
    event = HealEvent(timestamp="t", method="vlm", coordinates=[-5, 6],
                      duration_ms=1.0, locator_version="v2",
                      screen_region=[-10, 0, 10, 20], action="click",
                      action_verified=False)
    temp_log.append(event)
    assert temp_log.list_events() == [event]


def test_heal_stats_report_verification_apart_from_hits():
    from je_auto_control.utils.heal_analytics import heal_stats
    events = [
        HealEvent("t", "image", [1, 1], 1.0),
        HealEvent("t", "vlm", [1, 1], 1.0, action="click", action_verified=True),
        HealEvent("t", "vlm", [1, 1], 1.0, action="click", action_verified=False),
        HealEvent("t", "vlm", [1, 1], 1.0, action="click"),
        {"method": "image", "coordinates": [1, 1], "duration_ms": 1.0},
    ]
    stats = heal_stats(events)
    assert stats["healed"] == 5
    assert stats["action_verification"] == {
        "actions": 3, "verified": 1, "failed": 1, "unchecked": 1}
