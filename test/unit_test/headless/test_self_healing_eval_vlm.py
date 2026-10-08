"""A dataset can name a ``vlm`` strategy; the report counts its model usage.

Every backend here is a fake or the ``null`` backend: no request leaves the
process and no key is read.
"""
import json
import math

import numpy as np
import pytest

from je_auto_control.utils.cv2_utils.image_file import write_image
from je_auto_control.utils.self_healing import (
    EvaluationSample, HealingEvaluationError, ModelUsage, build_strategy,
    check_thresholds, evaluate_healing_dataset, evaluate_locators,
    format_comparison, template_match_strategy, vlm_strategy,
)
from je_auto_control.utils.self_healing.eval_vlm import usage_of_call
from je_auto_control.utils.vision.backends import NullVLMBackend, backend_by_name
from je_auto_control.utils.vision.backends._parse import read_usage
from je_auto_control.utils.vision.backends.base import VLMBackend, VLMRequestError

_PNG = bytes.fromhex("89504e470d0a1a0a")


class FakeBackend(VLMBackend):
    """Answers from a table keyed by description; records what it was sent."""

    name = "fake"
    available = True

    def __init__(self, answers, usage=None):
        self._answers = answers
        self._usage = usage
        self.seen = []

    def locate(self, image_bytes, description, model=None, image_mime="image/png"):
        self.seen.append((image_bytes, description, model))
        answer = self._answers.get(description)
        if isinstance(answer, Exception):
            raise answer
        self.last_usage = self._usage
        return answer


def _frame():
    frame = np.full((100, 160), 128, dtype=np.uint8)
    frame[30:50, 60:90] = 255
    return frame


def _samples():
    return [
        EvaluationSample("hit", _frame(), expected_box=(60, 30, 90, 50),
                         description="the white box"),
        EvaluationSample("wrong", _frame(), expected_box=(60, 30, 90, 50),
                         description="somewhere else"),
        EvaluationSample("absent", _frame(), expect_miss=True, description="nothing"),
    ]


_ANSWERS = {"the white box": (75, 40), "somewhere else": (5, 5), "nothing": None}


def test_a_vlm_version_is_scored_like_any_other_and_its_calls_are_counted():
    backend = FakeBackend(_ANSWERS, usage={"input_tokens": 1000, "output_tokens": 20})
    comparison = evaluate_locators(_samples(), {
        "vlm": vlm_strategy(backend, model="m-1",
                            price={"input_per_mtok": 5.0, "output_per_mtok": 25.0})})
    report = comparison.report("vlm")
    assert (report.correct, report.false_positive, report.true_negative) == (1, 1, 1)
    assert report.usage == ModelUsage(3, 3000, 60, report.usage.cost)
    assert math.isclose(report.usage.cost, 3 * (1000 * 5.0 + 20 * 25.0) / 1e6)
    row = comparison.results[0]
    assert row.usage.calls == 1 and row.to_dict()["model_calls"] == 1
    assert all(image.startswith(_PNG) and model == "m-1" for image, _d, model in backend.seen)
    assert "model calls  3" in format_comparison(comparison)


def test_tokens_and_cost_stay_none_when_the_backend_reports_nothing():
    comparison = evaluate_locators(_samples(), {"vlm": vlm_strategy(FakeBackend(_ANSWERS))})
    data = comparison.report("vlm").to_dict()
    assert (data["model_calls"], data["input_tokens"], data["output_tokens"], data["cost"]) == (
        3, None, None, None)


def test_a_template_version_reports_zero_calls_and_no_tokens():
    sample = EvaluationSample("t", _frame(), expected_box=(60, 30, 90, 50),
                              template=_frame()[25:55, 55:95])
    comparison = evaluate_locators([sample], {"v1": template_match_strategy(0.9)})
    data = comparison.report("v1").to_dict()
    assert data["correct"] == 1
    assert (data["model_calls"], data["input_tokens"], data["cost"]) == (0, None, None)
    assert "model calls" not in format_comparison(comparison)


def test_the_region_crop_is_what_the_model_sees_and_the_reply_is_mapped_back():
    backend = FakeBackend({"box": (15, 10)})
    sample = EvaluationSample(
        "hidpi", np.full((200, 320), 9, dtype=np.uint8), expected_box=(-1900, -290, -1880, -270),
        origin=(-1920, -300), scale=2.0, region=(-1900, -290, -1840, -250), description="box")
    comparison = evaluate_locators([sample], {"vlm": vlm_strategy(backend)})
    row = comparison.results[0]
    # region -> frame pixels (40, 20)-(160, 100); reply (15, 10) -> frame (55, 30)
    # -> screen (-1920 + 27, -300 + 15)
    assert row.coordinates == (-1893, -285) and row.outcome == "correct"
    image = backend.seen[0][0]
    assert (int.from_bytes(image[16:20], "big"), int.from_bytes(image[20:24], "big")) == (120, 80)


def test_a_reply_outside_the_image_is_a_miss_and_still_a_call():
    comparison = evaluate_locators(
        [EvaluationSample("off", _frame(), expected_box=(60, 30, 90, 50), description="d")],
        {"vlm": vlm_strategy(FakeBackend({"d": (500, 40)}))})
    row = comparison.results[0]
    assert (row.outcome, row.located, row.usage.calls) == ("miss", False, 1)


def test_a_failed_request_is_an_error_and_a_call_and_no_description_is_neither():
    samples = [
        EvaluationSample("boom", _frame(), expected_box=(60, 30, 90, 50), description="boom"),
        EvaluationSample("silent", _frame(), expected_box=(60, 30, 90, 50)),
    ]
    backend = FakeBackend({"boom": VLMRequestError("rate limited")})
    comparison = evaluate_locators(samples, {"vlm": vlm_strategy(backend)})
    boom, silent = comparison.results
    assert boom.outcome == "error" and "rate limited" in boom.error and boom.usage.calls == 1
    assert silent.outcome == "error" and "no description" in silent.error
    assert silent.usage.calls == 0
    assert comparison.report("vlm").usage.calls == 1


def test_the_null_backend_makes_no_call_and_every_sample_an_error():
    comparison = evaluate_locators(_samples(), {"vlm": vlm_strategy(NullVLMBackend())})
    report = comparison.report("vlm")
    assert (report.error, report.usage.calls) == (3, 0)
    assert isinstance(backend_by_name("null"), NullVLMBackend)


def test_thresholds_can_bound_model_calls_and_cost():
    backend = FakeBackend(_ANSWERS, usage={"input_tokens": 10, "output_tokens": 1, "cost": 0.5})
    comparison = evaluate_locators(_samples(), {"vlm": vlm_strategy(backend)})
    assert check_thresholds(comparison, {"vlm": {"max_model_calls": 3, "max_cost": 1.5}}) == []
    problems = check_thresholds(comparison, {"vlm": {"max_model_calls": 2, "max_cost": 1.0}})
    assert len(problems) == 2


def _dataset(tmp_path, versions):
    frame = np.zeros((100, 160, 3), dtype=np.uint8)
    frame[30:50, 60:90] = (0, 0, 255)          # BGR red box
    write_image(tmp_path / "frame.png", frame)
    write_image(tmp_path / "template.png", frame[25:55, 55:95])
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps({
        "samples": [{"id": "red", "frame": "frame.png", "template": "template.png",
                     "expected_box": [60, 30, 90, 50], "description": "the red box"}],
        "versions": versions,
    }), encoding="utf-8")
    return path


def test_a_dataset_file_names_a_vlm_version_and_a_template_one_on_the_same_frame(tmp_path):
    backend = FakeBackend({"the red box": (70, 40)},
                          usage={"input_tokens": 800, "output_tokens": 12})
    path = _dataset(tmp_path, {
        "template": {"strategy": "template", "threshold": 0.9},
        "model": {"strategy": "vlm", "backend": "fake", "model": "m-2",
                  "price": {"input_per_mtok": 1.0, "output_per_mtok": 2.0}}})
    payload = evaluate_healing_dataset(path, backends={"fake": backend})
    assert payload["versions"]["template"]["correct"] == 1
    assert payload["versions"]["template"]["model_calls"] == 0
    model = payload["versions"]["model"]
    assert (model["correct"], model["model_calls"], model["input_tokens"],
            model["output_tokens"]) == (1, 1, 800, 12)
    assert math.isclose(model["cost"], (800 * 1.0 + 12 * 2.0) / 1e6, abs_tol=1e-6)
    hashes = {row["frame_hash"] for row in payload["results"]}
    assert len(hashes) == 1     # both versions were given the one frame
    # The model was shown colour: a red pixel survives the PNG round trip.
    import cv2
    shown = cv2.imdecode(np.frombuffer(backend.seen[0][0], np.uint8), cv2.IMREAD_COLOR)
    assert tuple(int(value) for value in shown[40, 70]) == (0, 0, 255)


def test_the_null_backend_can_be_named_from_json(tmp_path):
    payload = evaluate_healing_dataset(
        _dataset(tmp_path, {"model": {"strategy": "vlm", "backend": "null"}}))
    assert payload["versions"]["model"]["error"] == 1
    assert payload["versions"]["model"]["model_calls"] == 0


@pytest.mark.parametrize("config, message", [
    ({"strategy": "vlm", "threshold": 0.9}, "unknown strategy option"),
    ({"strategy": "vlm", "backend": "nonesuch"}, "unknown VLM backend"),
    ({"strategy": "vlm", "backend": 3}, "backend must be a name"),
    ({"strategy": "vlm", "price": {"input_per_mtok": 1}}, "price must be an object"),
    ({"strategy": "vlm", "price": {"input_per_mtok": "x", "output_per_mtok": 1}},
     "price values must be numbers"),
    ({"strategy": "vlm", "price": {"input_per_mtok": -1, "output_per_mtok": 1}},
     "must not be negative"),
    ({"strategy": "ocr"}, "unknown strategy"),
    ({"strategy": ["vlm"]}, "unknown strategy"),
])
def test_a_malformed_vlm_version_is_refused(config, message):
    with pytest.raises(HealingEvaluationError, match=message):
        build_strategy(config)


def test_usage_is_read_from_sdk_responses_and_ignored_when_absent():
    class _Usage:
        input_tokens, output_tokens = 12, 3
        prompt_tokens, completion_tokens = 7, 2

    class _Response:
        usage = _Usage()

    assert read_usage(_Response(), "input_tokens", "output_tokens") == {
        "input_tokens": 12, "output_tokens": 3}
    assert read_usage(_Response(), "prompt_tokens", "completion_tokens") == {
        "input_tokens": 7, "output_tokens": 2}
    assert read_usage(object(), "input_tokens", "output_tokens") is None
    assert usage_of_call(None, (1.0, 1.0)) == ModelUsage(calls=1)
    assert usage_of_call({"input_tokens": True, "output_tokens": 2}, (1.0, 1.0)) == ModelUsage(
        1, None, 2, None)


def test_the_anthropic_backend_records_usage_from_an_injected_client():
    from je_auto_control.utils.vision.backends.anthropic_backend import AnthropicVLMBackend

    class _Block:
        type, text = "text", "(12, 34)"

    class _Usage:
        input_tokens, output_tokens = 321, 9

    class _Response:
        content, usage = [_Block()], _Usage()

    class _Messages:
        @staticmethod
        def create(**_kwargs):
            return _Response()

    class _Client:
        messages = _Messages()

    backend = AnthropicVLMBackend.__new__(AnthropicVLMBackend)
    backend._client, backend.available = _Client(), True
    backend.locate(b"not-a-png", "anything", model="m", image_mime="image/jpeg")
    assert backend.last_usage == {"input_tokens": 321, "output_tokens": 9}
