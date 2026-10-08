"""Built-in strategy versions and the file-based dataset for heal evaluation.

:mod:`evaluation` scores any callable; this module supplies the ones that can
be named from JSON, so the executor, the MCP tool and the GUI produce the same
report from the same dataset file:

* :func:`template_match_strategy` — OpenCV template match on the sample's
  frame, confined to the request's region, optionally trying the template at
  several scales. Coordinates go through :meth:`LocateRequest.to_screen`, so a
  hit on a HiDPI or negative-origin frame comes back as a screen point;
* :func:`load_evaluation_dataset` / :func:`evaluate_healing_dataset` — a JSON file of
  frame images, labels, version configs and thresholds.

Nothing here captures the screen. A version may name the ``vlm`` strategy
(:mod:`eval_vlm`), which asks a ``utils/vision`` backend about the sample's
own frame; that calls a model, and against a real backend it costs money.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from je_auto_control.utils.self_healing.eval_vlm import STRATEGY_VLM, vlm_strategy
from je_auto_control.utils.self_healing.evaluation import (
    EvaluationSample, HealingComparison, HealingEvaluationError, LocateRequest,
    LocatorStrategy, Point, check_thresholds, evaluate_locators,
)

#: A pixel-identical match scores 0.99999905 in float32 (see template_detection).
_SCORE_EPSILON = 1e-5

DATASET_SCHEMA_VERSION = 1
STRATEGY_TEMPLATE = "template"

PathLike = Union[str, "os.PathLike[str]"]


def _gray(image: Any) -> Any:
    """``image`` (path or array; a 3-D array is RGB) as a 2-D ``uint8`` array."""
    import cv2
    import numpy as np
    if isinstance(image, (str, os.PathLike)):
        from je_auto_control.utils.cv2_utils.image_file import read_image
        return read_image(os.fspath(image), cv2.IMREAD_GRAYSCALE)
    array = np.asarray(image)
    if array.ndim == 3 and array.shape[2] == 1:
        array = array[:, :, 0]
    if array.ndim == 3:
        array = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    if array.ndim != 2:
        raise ValueError(f"expected a 2-D or 3-D image, got shape {array.shape}")
    return array


def _best_match(area: Any, template: Any, scales: Sequence[float],
                ) -> Tuple[float, Tuple[int, int], Tuple[int, int]]:
    """Best ``(score, (left, top), (width, height))`` over ``scales``; score -1 if none fits."""
    import cv2
    best: Tuple[float, Tuple[int, int], Tuple[int, int]] = (-1.0, (0, 0), (0, 0))
    for scale in scales:
        scaled = template if math.isclose(scale, 1.0) else cv2.resize(
            template, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
        height, width = scaled.shape[:2]
        if height < 1 or width < 1 or height > area.shape[0] or width > area.shape[1]:
            continue
        scores = cv2.matchTemplate(area, scaled, cv2.TM_CCOEFF_NORMED)
        _low, high, _low_at, at = cv2.minMaxLoc(scores)
        if high > best[0]:
            best = (float(high), (int(at[0]), int(at[1])), (int(width), int(height)))
    return best


def template_match_strategy(threshold: float = 0.9,
                            scales: Sequence[float] = (1.0,),
                            template: Any = None) -> LocatorStrategy:
    """A strategy version that template-matches inside the request's frame.

    ``scales`` are factors applied to the template before matching; add the
    display scales the template may meet to make a version tolerant of them.
    ``template`` overrides the sample's own, which is how two revisions of one
    template are compared on the same frames.
    """
    limit = float(threshold)
    if not 0.0 <= limit <= 1.0:
        raise HealingEvaluationError(f"threshold must be between 0 and 1, got {threshold!r}")
    factors = tuple(float(scale) for scale in scales)
    if not factors or any(scale <= 0 for scale in factors):
        raise HealingEvaluationError(f"scales must be positive numbers, got {scales!r}")
    effective = min(limit, 1.0 - _SCORE_EPSILON)

    def locate(request: LocateRequest) -> Optional[Point]:
        source = template if template is not None else request.template
        if source is None:
            raise ValueError(f"sample {request.sample_id!r} has no template")
        frame = _gray(request.frame)
        box = request.frame_box(frame.shape[1], frame.shape[0])
        if box is None:
            return None
        left, top, right, bottom = box
        import cv2
        try:
            score, (at_x, at_y), (width, height) = _best_match(
                frame[top:bottom, left:right], _gray(source), factors)
        except cv2.error as error:
            # A pixel type OpenCV cannot match is this sample's error, in a
            # type the evaluation records instead of one that ends the run.
            raise ValueError(f"cannot match template: {error}") from error
        if score < effective:
            return None
        return request.to_screen(left + at_x + width / 2.0, top + at_y + height / 2.0)

    return locate


_OPTIONS = {
    STRATEGY_TEMPLATE: frozenset({"strategy", "threshold", "scales"}),
    STRATEGY_VLM: frozenset({"strategy", "backend", "model", "price"}),
}


def _named_backend(name: Any, backends: Optional[Mapping[str, Any]]) -> Any:
    """The VLM backend a version names; ``None`` means "pick from the environment"."""
    if name is None:
        return None
    if backends is not None and name in backends:
        return backends[name]
    if not isinstance(name, str):
        raise HealingEvaluationError(f"backend must be a name, got {name!r}")
    from je_auto_control.utils.vision.backends import backend_by_name
    from je_auto_control.utils.vision.backends.base import VLMNotAvailableError
    try:
        return backend_by_name(name)
    except VLMNotAvailableError as error:
        raise HealingEvaluationError(str(error)) from error


def build_strategy(config: Mapping[str, Any],
                   backends: Optional[Mapping[str, Any]] = None) -> LocatorStrategy:
    """Build a strategy from a version config.

    ``{"strategy": "template", "threshold", "scales"}`` or
    ``{"strategy": "vlm", "backend", "model", "price"}``. A ``vlm`` version's
    ``backend`` is ``"anthropic"``, ``"openai"``, ``"null"`` or a key of
    ``backends`` (objects supplied by the caller -- how a test passes a fake);
    without one, the backend ``get_backend()`` picks from the environment.
    """
    if not isinstance(config, Mapping):
        raise HealingEvaluationError(f"a version must be an object, got {config!r}")
    kind = config.get("strategy", STRATEGY_TEMPLATE)
    allowed = _OPTIONS.get(kind) if isinstance(kind, str) else None
    if allowed is None:
        raise HealingEvaluationError(
            f"unknown strategy {kind!r}; built-in strategies: {sorted(_OPTIONS)}")
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise HealingEvaluationError(f"unknown strategy option(s) {unknown}")
    if kind == STRATEGY_VLM:
        return vlm_strategy(_named_backend(config.get("backend"), backends),
                            model=config.get("model"), price=config.get("price"))
    return template_match_strategy(config.get("threshold", 0.9), config.get("scales", (1.0,)))


@dataclass(frozen=True)
class EvaluationDataset:
    """A loaded dataset file: samples, version configs and thresholds."""

    path: Path
    samples: Tuple[EvaluationSample, ...]
    versions: Mapping[str, Mapping[str, Any]]
    thresholds: Mapping[str, Mapping[str, float]]


def _inside_root(root: Path, relative: Any, what: str) -> Path:
    """``relative`` resolved under ``root``; a path that leaves it is refused."""
    if not isinstance(relative, str) or not relative:
        raise HealingEvaluationError(f"{what} must be a relative file path, got {relative!r}")
    resolved = Path(os.path.realpath(root / relative))
    if os.path.commonpath([str(root), str(resolved)]) != str(root):
        raise HealingEvaluationError(f"{what} {relative!r} is outside the dataset directory")
    if not resolved.is_file():
        raise HealingEvaluationError(f"{what} {relative!r} does not exist")
    return resolved


def _rgb(path: str) -> Any:
    """The image at ``path`` as an RGB array (what a model is shown)."""
    import cv2
    from je_auto_control.utils.cv2_utils.image_file import read_image
    return cv2.cvtColor(read_image(path, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def _sample_from(entry: Any, root: Path, color: bool = False) -> EvaluationSample:
    if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
        raise HealingEvaluationError(f"a sample must be an object with a string id, got {entry!r}")
    sample_id = entry["id"]
    template = entry.get("template")
    try:
        frame_path = str(_inside_root(root, entry.get("frame"), f"{sample_id}: frame"))
        frame = _rgb(frame_path) if color else _gray(frame_path)
    except ValueError as error:
        raise HealingEvaluationError(f"{sample_id}: {error}") from error
    return EvaluationSample(
        sample_id=sample_id, frame=frame,
        expected_box=entry.get("expected_box"),
        origin=entry.get("origin", (0, 0)), scale=entry.get("scale", 1.0),
        region=entry.get("region"), expect_miss=bool(entry.get("expect_miss", False)),
        template=(None if template is None
                  else str(_inside_root(root, template, f"{sample_id}: template"))),
        description=entry.get("description"))


def load_evaluation_dataset(path: PathLike, *, color: bool = False) -> EvaluationDataset:
    """Load a dataset JSON file; image paths are relative to its directory.

    Frames are loaded in grayscale unless ``color`` is true (RGB), which a
    version that shows the frame to a model needs; the template strategy
    converts either to gray itself, so every version still gets one frame.

    ::

        {"schema_version": 1,
         "samples": [{"id": "ok", "frame": "frames/ok.png", "template": "t.png",
                      "expected_box": [10, 20, 50, 40], "origin": [0, 0],
                      "scale": 1.0, "region": null, "expect_miss": false}],
         "versions": {"v1": {"strategy": "template", "threshold": 0.9}},
         "thresholds": {"v1": {"min_correct": 1, "max_false_positive": 0}}}

    A sample with neither ``expected_box`` nor ``expect_miss`` is unlabelled.
    """
    file_path = Path(os.path.realpath(os.fspath(path)))
    try:
        data = json.loads(file_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise HealingEvaluationError(f"cannot read dataset {file_path}: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("samples"), list):
        raise HealingEvaluationError(f"dataset {file_path} needs a 'samples' list")
    if data.get("schema_version", DATASET_SCHEMA_VERSION) != DATASET_SCHEMA_VERSION:
        raise HealingEvaluationError(
            f"dataset schema_version {data.get('schema_version')!r} is not "
            f"{DATASET_SCHEMA_VERSION}")
    versions = data.get("versions") or {}
    thresholds = data.get("thresholds") or {}
    if not isinstance(versions, dict) or not isinstance(thresholds, dict):
        raise HealingEvaluationError("'versions' and 'thresholds' must be objects")
    samples = tuple(_sample_from(entry, file_path.parent, color)
                    for entry in data["samples"])
    return EvaluationDataset(path=file_path, samples=samples,
                             versions=versions, thresholds=thresholds)


def comparison_payload(comparison: HealingComparison,
                       thresholds: Mapping[str, Mapping[str, float]],
                       ) -> Dict[str, Any]:
    """``comparison.to_dict()`` plus the threshold verdict, as every surface returns it."""
    violations: List[str] = check_thresholds(comparison, thresholds)
    payload = comparison.to_dict()
    payload["thresholds"] = {name: dict(limits) for name, limits in thresholds.items()}
    payload["violations"] = violations
    payload["passed"] = not violations
    return payload


#: Columns of :func:`comparison_rows`, in display order.
COMPARISON_COLUMNS = (
    "version", "located", "accuracy", "false_positive", "recovery",
    "p50_ms", "p95_ms", "model_calls", "tokens", "cost",
)
_NOT_REPORTED = "-"


def _ratio_text(ratio: Any) -> str:
    """``3/4 (75.0%)`` from a ``Ratio.to_dict()``; ``n/a`` over nothing."""
    if not isinstance(ratio, Mapping):
        return _NOT_REPORTED
    value = ratio.get("value")
    shown = "n/a" if value is None else f"{float(value) * 100:.1f}%"
    return f"{ratio.get('numerator')}/{ratio.get('denominator')} ({shown})"


def _shown(value: Any) -> str:
    return _NOT_REPORTED if value is None else str(value)


def comparison_rows(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """One display row per version of an evaluation report, baseline first.

    ``payload`` is what :func:`evaluate_healing_dataset` returns. Every cell is
    text keyed by :data:`COMPARISON_COLUMNS`, plus ``baseline`` (bool). A rate
    keeps its counts (``3/4 (75.0%)``); a value nobody reported -- tokens or
    cost of a version that called no model -- is ``-``, not ``0``.
    """
    versions = payload.get("versions")
    if not isinstance(versions, Mapping):
        raise HealingEvaluationError("not an evaluation report: it has no 'versions'")
    baseline = payload.get("baseline")
    rows: List[Dict[str, Any]] = []
    for name, report in versions.items():
        tokens = (report.get("input_tokens"), report.get("output_tokens"))
        row = {
            "version": str(name), "baseline": name == baseline,
            "located": _ratio_text(report.get("hit_rate")),
            "accuracy": _ratio_text(report.get("accuracy")),
            "false_positive": _ratio_text(report.get("false_positive_rate")),
            "recovery": _ratio_text(report.get("recovery_rate")),
            "p50_ms": _shown(report.get("p50_ms")), "p95_ms": _shown(report.get("p95_ms")),
            "model_calls": _shown(report.get("model_calls")),
            "tokens": (_NOT_REPORTED if tokens == (None, None)
                       else f"{_shown(tokens[0])} / {_shown(tokens[1])}"),
            "cost": _shown(report.get("cost")),
        }
        rows.append(row)
    # Stable: the baseline first, the rest in the order the report lists them.
    return sorted(rows, key=lambda row: not row["baseline"])


def _names_vlm(configs: Mapping[str, Any]) -> bool:
    return any(isinstance(config, Mapping) and config.get("strategy") == STRATEGY_VLM
               for config in configs.values())


def evaluate_healing_dataset(path: PathLike,
                     versions: Optional[Mapping[str, Mapping[str, Any]]] = None,
                     backends: Optional[Mapping[str, Any]] = None,
                     ) -> Dict[str, Any]:
    """Evaluate a dataset file and return the JSON-safe report.

    ``versions`` replaces the file's own version configs when given, and
    ``backends`` maps a name a ``vlm`` version may use to a backend object.
    The report is :meth:`HealingComparison.to_dict` plus ``dataset``,
    ``thresholds``, ``violations`` and ``passed``. A ``vlm`` version against a
    real backend sends every frame to that service.
    """
    dataset = load_evaluation_dataset(path)
    configs = dataset.versions if versions is None else versions
    if not configs:
        raise HealingEvaluationError(f"dataset {dataset.path} names no versions to compare")
    if _names_vlm(configs):
        dataset = load_evaluation_dataset(path, color=True)
    strategies = {name: build_strategy(config, backends)
                  for name, config in configs.items()}
    comparison = evaluate_locators(dataset.samples, strategies)
    payload = comparison_payload(comparison, dataset.thresholds)
    payload["dataset"] = str(dataset.path)
    return payload


__all__ = [
    "COMPARISON_COLUMNS", "DATASET_SCHEMA_VERSION", "EvaluationDataset",
    "STRATEGY_TEMPLATE", "STRATEGY_VLM",
    "build_strategy", "comparison_payload", "comparison_rows", "evaluate_healing_dataset",
    "load_evaluation_dataset", "template_match_strategy",
]
