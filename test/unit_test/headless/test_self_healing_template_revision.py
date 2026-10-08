"""Candidate template revisions, the dataset file, and the fixed benchmark.

Frames and templates are arrays written to ``tmp_path``; the screen is never
captured and the template store lives under ``tmp_path`` too.
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from je_auto_control.utils.cv2_utils.image_file import write_image
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.self_healing import template_revision as revision_mod
from je_auto_control.utils.self_healing.eval_strategies import (
    build_strategy, evaluate_healing_dataset, load_evaluation_dataset,
    template_match_strategy,
)
from je_auto_control.utils.self_healing.evaluation import (
    EvaluationSample, HealingEvaluationError, evaluate_locators,
)
from je_auto_control.utils.self_healing.template_revision import (
    STATUS_ACCEPTED, STATUS_PENDING, STATUS_REVERTED, TemplateRevisionError,
    TemplateRevisionStore,
)

_REPO = Path(__file__).resolve().parents[3]


def _patch(seed: int, width: int = 30, height: int = 20) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 255, (height, width), dtype=np.uint8)


def _frame(*placed) -> np.ndarray:
    """A flat frame with each ``(patch, left, top)`` pasted in."""
    frame = np.full((120, 200), 128, dtype=np.uint8)
    for patch, left, top in placed:
        frame[top:top + patch.shape[0], left:left + patch.shape[1]] = patch
    return frame


OLD, NEW, OTHER = _patch(1), _patch(2), _patch(3)


@pytest.fixture
def files(tmp_path):
    """The live template (old look), candidates, and a labelled dataset."""
    paths = {"template": tmp_path / "live" / "button.png",
             "new": tmp_path / "new.png", "other": tmp_path / "other.png",
             "dataset": tmp_path / "data" / "dataset.json"}
    for path in (paths["template"], paths["dataset"]):
        path.parent.mkdir(parents=True)
    write_image(paths["template"], OLD)
    write_image(paths["new"], NEW)
    write_image(paths["other"], OTHER)
    data_dir = paths["dataset"].parent
    write_image(data_dir / "new_look.png", _frame((NEW, 50, 40)))
    write_image(data_dir / "other_only.png", _frame((OTHER, 10, 10)))
    write_image(data_dir / "t.png", OLD)
    paths["dataset"].write_text(json.dumps({
        "schema_version": 1,
        "samples": [
            {"id": "new-look", "frame": "new_look.png", "template": "t.png",
             "expected_box": [50, 40, 80, 60]},
            {"id": "absent", "frame": "other_only.png", "template": "t.png",
             "expect_miss": True},
        ],
        "versions": {"v1": {"strategy": "template", "threshold": 0.9}},
        "thresholds": {"v1": {"min_correct": 1}},
    }), encoding="utf-8")
    return paths


@pytest.fixture
def store(tmp_path):
    return TemplateRevisionStore(tmp_path / "revisions")


# --- propose / preview / accept / revert ---------------------------------


def test_propose_leaves_the_template_alone(store, files):
    before = files["template"].read_bytes()
    revision = store.propose(files["template"], files["new"], source="vlm", note="redesign")
    assert revision.status == STATUS_PENDING and revision.validated is False
    assert files["template"].read_bytes() == before
    assert Path(revision.candidate_file).read_bytes() == files["new"].read_bytes()
    assert [item.revision_id for item in store.list_revisions()] == [revision.revision_id]
    assert store.get(revision.revision_id).source == "vlm"


def test_unvalidated_candidate_is_not_accepted(store, files):
    before = files["template"].read_bytes()
    revision = store.propose(files["template"], files["new"])
    preview = store.preview(revision.revision_id)
    assert preview["comparison"] is None
    assert preview["current"]["width"] == 30 and preview["candidate"]["height"] == 20
    assert preview["current"]["sha256"] != preview["candidate"]["sha256"]
    with pytest.raises(TemplateRevisionError, match="not been validated"):
        store.accept(revision.revision_id)
    assert files["template"].read_bytes() == before


def test_preview_with_a_dataset_validates_then_accept_and_revert(store, files):
    before = files["template"].read_bytes()
    revision = store.propose(files["template"], files["new"])
    preview = store.preview(revision.revision_id, dataset_path=files["dataset"])
    versions = preview["comparison"]["versions"]
    assert versions["current"]["correct"] == 0 and versions["current"]["miss"] == 1
    assert versions["candidate"]["correct"] == 1
    assert versions["candidate"]["false_positive"] == 0
    assert preview["revision"]["validated"] is True
    assert files["template"].read_bytes() == before, "preview must not write the template"

    accepted = store.accept(revision.revision_id)
    assert accepted.status == STATUS_ACCEPTED
    assert files["template"].read_bytes() == files["new"].read_bytes()
    assert Path(accepted.backup_file).read_bytes() == before
    with pytest.raises(TemplateRevisionError, match="already accepted"):
        store.accept(revision.revision_id)

    reverted = store.revert(revision.revision_id)
    assert reverted.status == STATUS_REVERTED
    assert files["template"].read_bytes() == before
    with pytest.raises(TemplateRevisionError, match="not accepted"):
        store.revert(revision.revision_id)


def test_a_candidate_that_hits_the_wrong_thing_is_not_validated(store, files):
    # OTHER is on the frame that expects a miss: located, and wrong.
    revision = store.propose(files["template"], files["other"])
    preview = store.preview(revision.revision_id, dataset_path=files["dataset"])
    candidate = preview["comparison"]["versions"]["candidate"]
    assert candidate["false_positive"] == 1 and candidate["located"] == 1
    assert preview["revision"]["validated"] is False
    with pytest.raises(TemplateRevisionError):
        store.accept(revision.revision_id)


def test_preview_takes_samples_built_in_code(store, files):
    revision = store.propose(files["template"], files["new"])
    samples = [EvaluationSample("s", _frame((NEW, 5, 5)), expected_box=(5, 5, 35, 25))]
    preview = store.preview(revision.revision_id, samples=samples)
    assert preview["revision"]["validated"] is True
    with pytest.raises(TemplateRevisionError):
        store.preview(revision.revision_id, samples=samples, dataset_path=files["dataset"])


def test_allow_unvalidated_is_an_explicit_opt_in(store, files):
    revision = store.propose(files["template"], files["new"])
    accepted = store.accept(revision.revision_id, allow_unvalidated=True)
    assert accepted.status == STATUS_ACCEPTED and accepted.validated is False


def test_a_template_changed_underneath_is_never_overwritten(store, files):
    revision = store.propose(files["template"], files["new"])
    write_image(files["template"], _patch(9))
    edited = files["template"].read_bytes()
    with pytest.raises(TemplateRevisionError, match="changed since"):
        store.accept(revision.revision_id, allow_unvalidated=True)
    assert files["template"].read_bytes() == edited

    second = store.propose(files["template"], files["new"])
    store.accept(second.revision_id, allow_unvalidated=True)
    write_image(files["template"], _patch(10))
    with pytest.raises(TemplateRevisionError, match="changed since"):
        store.revert(second.revision_id)


def test_bad_inputs_raise_the_framework_error(store, files, tmp_path):
    with pytest.raises(TemplateRevisionError):
        store.propose(tmp_path / "missing.png", files["new"])
    with pytest.raises(TemplateRevisionError, match="identical"):
        store.propose(files["template"], files["template"])
    for bad in ("../../etc", "", "zzzzzzzzzzzz", "0123456789ab"):
        with pytest.raises(TemplateRevisionError):
            store.get(bad)
    assert issubclass(TemplateRevisionError, AutoControlException)


def test_module_functions_use_the_default_store(monkeypatch, files, tmp_path):
    monkeypatch.setattr(revision_mod, "default_revision_root", lambda: tmp_path / "home-store")
    revision = revision_mod.propose_template_revision(files["template"], files["new"])
    assert (tmp_path / "home-store" / "index.json").is_file()
    assert revision_mod.list_template_revisions()[0].revision_id == revision.revision_id
    revision_mod.preview_template_revision(revision.revision_id, dataset_path=files["dataset"])
    revision_mod.accept_template_revision(revision.revision_id)
    assert revision_mod.revert_template_revision(revision.revision_id).status == STATUS_REVERTED


# --- template strategy and dataset file ----------------------------------


def test_template_strategy_honours_region_origin_and_scale():
    import cv2
    twice = cv2.resize(NEW, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_NEAREST)
    frame = np.full((240, 400), 128, dtype=np.uint8)
    frame[20:60, 20:80] = twice          # first copy, screen (-990, -490)
    frame[160:200, 300:360] = twice      # second copy, screen (-850, -420)
    sample = EvaluationSample(
        "s", frame, expected_box=(-850, -420, -820, -400), origin=(-1000, -500),
        scale=2.0, region=(-900, -450, -800, -380), template=NEW)
    comparison = evaluate_locators([sample], {
        "exact": template_match_strategy(0.9),
        "scaled": template_match_strategy(0.9, scales=(1.0, 2.0)),
    })
    assert comparison.report("exact").miss == 1
    assert comparison.report("scaled").correct == 1
    assert comparison.results[1].coordinates == (-835, -410)
    assert comparison.report("scaled").recovery_rate.numerator == 1


def test_region_outside_the_frame_is_a_miss_not_an_error():
    sample = EvaluationSample("s", _frame((NEW, 5, 5)), expected_box=(5, 5, 35, 25),
                              region=(5000, 5000, 5100, 5100), template=NEW)
    report = evaluate_locators([sample], {"v": template_match_strategy()}).report("v")
    assert report.miss == 1 and report.error == 0


def test_missing_template_is_an_error_outcome():
    sample = EvaluationSample("s", _frame(), expect_miss=True)
    report = evaluate_locators([sample], {"v": template_match_strategy()}).report("v")
    assert report.error == 1


def test_dataset_file_round_trip(files):
    dataset = load_evaluation_dataset(files["dataset"])
    assert [sample.sample_id for sample in dataset.samples] == ["new-look", "absent"]
    payload = evaluate_healing_dataset(files["dataset"])
    # The old template misses the redesigned control and rejects the other frame.
    assert payload["versions"]["v1"]["miss"] == 1
    assert payload["versions"]["v1"]["true_negative"] == 1
    assert payload["passed"] is False and len(payload["violations"]) == 1
    json.dumps(payload)


def test_dataset_paths_cannot_leave_the_dataset_directory(files):
    data = json.loads(files["dataset"].read_text(encoding="utf-8"))
    data["samples"][0]["frame"] = "../new.png"
    files["dataset"].write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(HealingEvaluationError, match="outside the dataset directory"):
        load_evaluation_dataset(files["dataset"])


@pytest.mark.parametrize("config", [
    {"strategy": "telepathy"}, {"threshold": 2}, {"scales": [0]},
    {"strategy": "template", "colour": "blue"},
])
def test_unknown_strategy_configs_are_rejected(config):
    with pytest.raises(HealingEvaluationError):
        build_strategy(config)


def test_unreadable_dataset_is_the_framework_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(HealingEvaluationError):
        evaluate_healing_dataset(bad)
    with pytest.raises(HealingEvaluationError):
        evaluate_healing_dataset(tmp_path / "missing.json")


# --- the fixed benchmark -------------------------------------------------


@pytest.fixture
def benchmark(monkeypatch):
    """``benchmarks/self_healing/run.py`` loaded with every capture path armed to fail."""
    from je_auto_control.utils.monitor_layout import logical_frame
    from je_auto_control.wrapper import auto_control_mouse

    def forbidden(*_args, **_kwargs):
        raise AssertionError("the benchmark touched the real screen or pointer")

    monkeypatch.setattr(logical_frame, "grab_logical", forbidden)
    monkeypatch.setattr(auto_control_mouse, "click_mouse", forbidden)
    monkeypatch.setattr(auto_control_mouse, "set_mouse_position", forbidden)
    saved_path = list(sys.path)
    spec = importlib.util.spec_from_file_location(
        "self_healing_benchmark_run", _REPO / "benchmarks" / "self_healing" / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    sys.path[:] = saved_path
    sys.modules.pop("synthetic", None)


def test_benchmark_counts_are_fixed(benchmark):
    payload = benchmark.report()
    versions = payload["versions"]
    assert payload["baseline"] == "v1-exact" and payload["passed"] is True
    exact, multi, loose = (versions[name] for name in (
        "v1-exact", "v2-multiscale", "v3-loose"))
    assert all(report["total"] == 10 and report["unknown"] == 1
               for report in (exact, multi, loose))
    assert (exact["correct"], exact["miss"], exact["true_negative"]) == (4, 3, 2)
    assert multi["accuracy"] == {"numerator": 8, "denominator": 9, "value": 0.8889}
    assert multi["recovery_rate"]["numerator"] == 2
    assert multi["recovery_rate"]["denominator"] == 3
    # The loose version locates more and is right less: that is the point.
    assert loose["located"] > multi["located"]
    assert loose["false_positive"] == 1
    assert loose["accuracy"]["numerator"] < multi["accuracy"]["numerator"]
    assert exact["p50_ms"] is not None and exact["p95_ms"] >= exact["p50_ms"]


def test_benchmark_covers_failing_scaled_and_negative_cases(benchmark):
    samples = {sample.sample_id: sample for sample in benchmark.synthetic.build_samples()}
    assert any(sample.scale != 1.0 for sample in samples.values())
    assert any(sample.origin[0] < 0 and sample.origin[1] < 0 for sample in samples.values())
    assert any(sample.region and sample.region[0] < 0 for sample in samples.values())
    assert any(sample.expect_miss for sample in samples.values())
    assert any(not sample.labelled for sample in samples.values())
    by_sample = {(row["sample_id"], row["version"]): row["outcome"]
                 for row in benchmark.report()["results"]}
    assert by_sample[("failing-restyled", "v3-loose")] == "miss"
    assert by_sample[("failing-decoy-only", "v3-loose")] == "false_positive"
    assert by_sample[("region-negative-origin", "v1-exact")] == "correct"
    assert by_sample[("negative-origin-scaled-125", "v2-multiscale")] == "correct"
    assert by_sample[("unlabelled", "v1-exact")] == "unknown"


def test_benchmark_is_deterministic_and_writes_json(benchmark, tmp_path, capsys):
    first, second = (benchmark.synthetic.build_samples() for _ in range(2))
    assert all(np.array_equal(a.frame, b.frame) for a, b in zip(first, second))
    out = tmp_path / "report.json"
    assert benchmark.main(["--check", "--json", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["passed"] is True
    assert "v2-multiscale" in capsys.readouterr().out
