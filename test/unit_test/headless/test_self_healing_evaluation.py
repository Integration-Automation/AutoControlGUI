"""Fixed-frame comparisons separate localization, verification and unknown labels."""
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from je_auto_control.utils.self_healing.evaluation import evaluate_locators
from je_auto_control.utils.self_healing.evaluation_models import EvaluationSample, LocatorCandidate
from je_auto_control.utils.self_healing.evaluation_models import HealingEvaluationError
from je_auto_control.utils.self_healing.evaluation_io import evaluate_healing_manifest, write_healing_report
from je_auto_control.utils.self_healing.frame_locators import TemplateFrameLocator, VLMFrameLocator
from je_auto_control.utils.vision.backends.base import VLMBackend

DATASET = Path(__file__).resolve().parents[3] / "benchmarks/self_healing"


def png(size=(40, 30)):
    stream = io.BytesIO()
    Image.new("RGB", size, "white").save(stream, format="PNG")
    return stream.getvalue()


class FixedLocator:
    def __init__(self, candidate):
        self.candidate = candidate
        self.seen = []

    def locate(self, sample):
        self.seen.append(sample)
        return self.candidate


def test_unlabelled_is_unknown():
    report = evaluate_locators([EvaluationSample("unknown", png())], {
        "v1": FixedLocator(LocatorCandidate((4, 5), "image")),
    })
    version = report.versions["v1"]
    assert version.unknown == 1
    assert version.accuracy.numerator == version.accuracy.denominator == 0
    assert version.accuracy.value is None
    assert report.attempts[0].correct is None


def test_false_positive_is_not_recovery():
    samples = [EvaluationSample("labelled", png(), expected_box=(0, 0, 10, 10))]
    bad = LocatorCandidate((20, 20), "vlm", fallback_used=True, verified=True)
    good = LocatorCandidate((4, 5), "vlm", fallback_used=True)
    report = evaluate_locators(samples, {"bad": FixedLocator(bad), "unverified": FixedLocator(good)})
    assert report.versions["bad"].false_positive.numerator == 1
    assert report.versions["bad"].recovery.numerator == 0
    assert report.versions["bad"].recovery.denominator == 1
    assert report.versions["unverified"].accuracy.numerator == 1
    assert report.versions["unverified"].recovery.denominator == 0
    assert report.versions["unverified"].verification_unknown == 1


def test_same_frame_versions_are_comparable():
    sample = EvaluationSample("shared", png(), expected_miss=True)
    left = FixedLocator(LocatorCandidate(None, "miss"))
    right = FixedLocator(LocatorCandidate((4, 5), "image"))
    report = evaluate_locators([sample], {"old": left, "new": right})
    assert left.seen[0] is right.seen[0] is sample
    assert report.attempts[0].frame_hash == report.attempts[1].frame_hash
    assert report.versions["old"].accuracy.numerator == 1
    assert report.versions["new"].false_positive.numerator == 1


def test_region_passed_to_both_strategies():
    sample = EvaluationSample("crop", png(), origin=(-100, -50), scale=2,
                              region=(-98, -48, -90, -40))
    image, vlm = FixedLocator(LocatorCandidate(None, "miss")), FixedLocator(LocatorCandidate(None, "miss"))
    evaluate_locators([sample], {"image": image, "vlm": vlm})
    assert image.seen[0].region == vlm.seen[0].region == (-98, -48, -90, -40)


def test_real_template_dataset_and_versioned_acceptance():
    report = evaluate_healing_manifest(DATASET / "dataset.json")
    thresholds = json.loads((DATASET / "acceptance.json").read_text(encoding="utf-8"))
    for name, expected in thresholds.items():
        actual = report.versions[name]
        assert actual.accuracy.numerator == expected["correct"]
        assert actual.accuracy.denominator == expected["labelled"]
        assert actual.unknown == expected["unknown"]
        assert actual.false_positive.numerator == expected["false_positive"]
        assert actual.recovery.value is None
    attempt = next(row for row in report.attempts if row.version == "new" and row.sample_id.startswith("negative"))
    assert attempt.candidate.coordinates == (-66, -29)
    assert attempt.correct is True and attempt.step_id == "scaled-submit"


def test_image_miss_and_vlm_use_same_crop_and_transform_without_capture(monkeypatch):
    frame = (DATASET / "fixtures/frame_new.png").read_bytes()
    sample = EvaluationSample("crop", frame, expected_box=(-70, -32, -61.5, -25.5),
                              origin=(-80, -40), scale=2, region=(-72, -34, -60, -24))
    seen = []

    class Backend(VLMBackend):
        available, name = True, "controlled"

        def locate(self, image_bytes, description, model=None, image_mime="image/png"):
            seen.append(image_bytes)
            return 12, 10

        def verify(self, *_args, **_kwargs):
            pytest.fail("no implicit post-operation verification")

    def forbidden(*_args, **_kwargs):
        pytest.fail("evaluation must not capture or click")

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical", forbidden)
    monkeypatch.setattr("je_auto_control.wrapper.auto_control_mouse.click_mouse", forbidden)
    vlm = VLMFrameLocator(Backend(), "submit", model="fake")
    image = TemplateFrameLocator((DATASET / "fixtures/old.png").read_bytes(), .99, vlm)
    result = image.locate(sample)
    assert result.coordinates == (-66, -29) and result.method == "vlm"
    assert result.verified is None and result.fallback_used
    assert [name for name, _ in result.timings_ms] == ["image", "fallback.vlm"]
    with Image.open(io.BytesIO(frame)) as original, Image.open(io.BytesIO(seen[0])) as actual:
        assert actual.size == (24, 20)
        assert actual.tobytes() == original.crop((16, 12, 40, 32)).tobytes()


def test_measured_percentiles_costs_and_verified_recovery(monkeypatch):
    ticks = iter([0, 1, 2, 4])
    monkeypatch.setattr("je_auto_control.utils.self_healing.evaluation.perf_counter", lambda: next(ticks))
    locator = FixedLocator(LocatorCandidate((4, 5), "vlm", fallback_used=True, verified=True, cost=.01))
    samples = [EvaluationSample(str(index), png(), expected_box=(0, 0, 10, 10)) for index in range(2)]
    version = evaluate_locators(samples, {"v1": locator}).versions["v1"]
    assert version.p50_ms == 1500 and version.p95_ms == 1950
    assert version.cost_total == .02 and version.cost_known == 2
    assert version.recovery.to_dict() == {"numerator": 2, "denominator": 2, "value": 1}


@pytest.mark.parametrize("fields", [
    {"scale": 0}, {"scale": float("nan")}, {"scale": True}, {"origin": (True, 0)},
    {"region": (-1, 0, 20, 20)}, {"expected_box": (0, 0, 0, 10)},
    {"expected_box": (0, 0, 10, 10), "expected_miss": True}, {"expected_miss": "false"},
    {"frame": bytearray(png())}, {"run_id": 1},
])
def test_invalid_samples_fail_at_boundary(fields):
    values = {"sample_id": "invalid", "frame": png(), **fields}
    with pytest.raises(HealingEvaluationError):
        EvaluationSample(**values)


def test_strategy_and_observer_errors_propagate_without_partial_report():
    seen = []
    signal = RuntimeError("strategy aborted")

    class Failure:
        def locate(self, sample):
            seen.append(sample.sample_id)
            raise signal

    samples = [EvaluationSample("first", png()), EvaluationSample("second", png())]
    with pytest.raises(RuntimeError) as caught:
        evaluate_locators(samples, {"v1": Failure()})
    assert caught.value is signal and seen == ["first"]
    with pytest.raises(RuntimeError) as caught:
        evaluate_locators(samples, {"v1": Failure()}, observer=lambda _: (_ for _ in ()).throw(signal))
    assert caught.value is signal and seen == ["first"]


def test_exports_escape_html_and_contain_provenance_without_images(tmp_path):
    sample = EvaluationSample("<script>probe</script>", png(), expected_miss=True, run_id="run", step_id="step")
    report = evaluate_locators([sample], {"<candidate>": FixedLocator(LocatorCandidate(None, "miss"))})
    json_path = write_healing_report(report, tmp_path / "report.json")
    html_path = write_healing_report(report, tmp_path / "report.html")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["attempts"][0]["run_id"] == "run" and "frame" not in payload["attempts"][0]
    html = html_path.read_text(encoding="utf-8")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert payload["versions"]["<candidate>"]["accuracy"]["value"] == 1


def test_manifest_nested_assets_cannot_escape_directory(tmp_path):
    path = tmp_path / "dataset/manifest.json"
    path.parent.mkdir()
    (tmp_path / "outside.png").write_bytes(png())
    path.write_text(json.dumps({"schema_version": 1, "samples": [{"id": "x", "frame": "../outside.png"}],
                                "versions": {"v1": {"template": "../outside.png"}}}), encoding="utf-8")
    from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError
    with pytest.raises(PathNotAllowedError):
        evaluate_healing_manifest(path)


@pytest.mark.parametrize("fields", [
    {"coordinates": (True, 0)}, {"coordinates": (float("inf"), 0)}, {"method": "bad"},
    {"method": "miss"}, {"cost": -1}, {"cost": float("nan")}, {"verified": "true"},
    {"backend": 1}, {"timings_ms": (("x", -1),)}, {"timings_ms": (("x", 1), ("x", 2))},
    {"timings_ms": (("x", 1, 2),)}, {"method": "vlm", "fallback_used": False},
])
def test_invalid_candidates_fail_at_boundary(fields):
    with pytest.raises(HealingEvaluationError):
        LocatorCandidate(**{"coordinates": (1, 2), "method": "image", **fields})


def test_unknown_empty_and_duplicate_populations_remain_explicit():
    locator = FixedLocator(LocatorCandidate(None, "miss"))
    empty = evaluate_locators([], {"v1": locator}).versions["v1"]
    assert empty.p50_ms is empty.p95_ms is empty.accuracy.value is empty.cost_total is None
    sample = EvaluationSample("duplicate", png())
    with pytest.raises(HealingEvaluationError):
        evaluate_locators([sample, sample], {"v1": locator})
    with pytest.raises(HealingEvaluationError):
        evaluate_locators([sample], {})
    with pytest.raises(HealingEvaluationError):
        evaluate_locators([sample], {"v1": object()})


def test_masked_snapshot_remains_safe_after_secret_scope_closes(tmp_path):
    from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope

    with secret_log_scope():
        remember_secret("sensitive-label")
        sample = EvaluationSample("sensitive-label", png(), run_id="sensitive-label", step_id="sensitive-label")
        locator = FixedLocator(LocatorCandidate((4, 5), "vlm", fallback_used=True, backend="sensitive-label"))
        report = evaluate_locators([sample], {"sensitive-label": locator})
    for suffix in ("json", "html"):
        path = write_healing_report(report, tmp_path / f"report.{suffix}")
        assert "sensitive-label" not in path.read_text(encoding="utf-8")
    with pytest.raises(TypeError):
        report.versions["new"] = report.versions["***"]


def test_constant_template_and_outside_vlm_point_are_refused():
    sample = EvaluationSample("probe", png())
    with pytest.raises(HealingEvaluationError, match="constant"):
        TemplateFrameLocator(png()).locate(sample)

    class Backend(VLMBackend):
        available = True

        def locate(self, *_args, **_kwargs):
            return 10000, 0

    with pytest.raises(HealingEvaluationError, match="outside"):
        VLMFrameLocator(Backend(), "probe").locate(sample)


@pytest.mark.parametrize("payload", [
    '{"schema_version":1,"schema_version":1,"samples":[],"versions":{}}',
    '{"schema_version":true,"samples":[],"versions":{}}',
    '{"schema_version":1,"samples":[],"versions":{}}',
    '{"schema_version":1,"samples":[{}],"versions":{}}',
    '{"schema_version":1,"samples":[],"versions":{},"unknown":1}',
])
def test_invalid_manifest_never_runs_a_strategy(tmp_path, payload):
    path = tmp_path / "invalid.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(HealingEvaluationError):
        evaluate_healing_manifest(path)
