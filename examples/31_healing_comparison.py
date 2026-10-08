"""Compare two versions of a locator on frames that carry the right answer.

The heal log (``19_self_healing_locator.py``) records *what* a locator did. It
cannot say whether that was right: a strategy that returns a confident wrong
point looks exactly like one that healed. An evaluation runs every version
over the **same** labelled frames and scores the answers::

    samples = [
        ac.EvaluationSample("login", frame, expected_box=(100, 60, 140, 84), template=tpl),
        ac.EvaluationSample("no-such-button", other_frame, expect_miss=True, template=tpl),
    ]
    comparison = ac.evaluate_locators(samples, {
        "v1": ac.template_match_strategy(threshold=0.9),
        "v2": ac.template_match_strategy(threshold=0.9, scales=(1.0, 1.5)),
    })
    print(comparison.report("v2").accuracy)          # e.g. 4/4 = 1.0
    print(comparison.failures("v1"))                 # which samples, and how

How answers are scored:

* ``correct`` -- the point is inside the sample's ``expected_box``;
* ``false_positive`` -- a point anywhere else, or any point on a sample that
  expects a miss. It was located, and it is not a recovery;
* ``miss`` / ``true_negative`` -- nothing returned, where something / nothing
  was expected;
* ``unknown`` -- the sample has no label; it counts toward no correctness rate.

Every rate carries its numerator and denominator, and a rate over nothing has
no value rather than a perfect one. Coordinates are *screen* coordinates:
``origin`` is the screen position of the frame's top-left pixel (negative for
a monitor left of the primary) and ``scale`` is frame pixels per screen unit,
so a HiDPI capture and a second monitor are scored in the space a click uses.

A strategy is any callable taking a ``LocateRequest`` and returning ``(x, y)``
or ``None`` -- wrap a VLM call in one to evaluate it the same way. Datasets
can also live in a JSON file (``ac.evaluate_healing_dataset(path)``,
``AC_self_heal_evaluate``, schema version 1) with pass/fail thresholds;
``benchmarks/self_healing/run.py`` is the maintained one.

Nothing here reads the screen or calls a model. ``--validate`` draws its
frames in memory and checks the scores; ``--dataset FILE`` evaluates a dataset
file of your own. Both are offline.
"""
import argparse
import json
import sys
from typing import List, Optional, Tuple

import cv2
import numpy as np

import je_auto_control as ac
# The threshold gate and the text table live beside the evaluator, not on the facade.
from je_auto_control.utils.self_healing.evaluation import check_thresholds, format_comparison

_TEMPLATE_SIZE = (40, 24)        # width, height in screen units


def draw_button(scale: float = 1.0, restyled: bool = False) -> np.ndarray:
    """The control being located, as a grayscale image at ``scale``."""
    width, height = (round(side * scale) for side in _TEMPLATE_SIZE)
    image = np.tile(np.linspace(70, 190, width, dtype=np.float32), (height, 1)).astype(np.uint8)
    cv2.rectangle(image, (0, 0), (width - 1, height - 1), 20, max(1, round(2 * scale)))
    cv2.circle(image, (height // 2, height // 2), height // 4, 250, -1)
    cv2.rectangle(image, (width // 2, height // 3), (width - round(6 * scale), height // 2), 240, -1)
    return 255 - image if restyled else image


def draw_frame(at: Optional[Tuple[int, int]], scale: float = 1.0,
               restyled: bool = False, seed: int = 7) -> np.ndarray:
    """A 320x200 (screen units) noisy frame with the button at ``at``, if any."""
    rng = np.random.default_rng(seed)
    frame = rng.integers(105, 135, size=(round(200 * scale), round(320 * scale)), dtype=np.uint8)
    if at is not None:
        button = draw_button(scale, restyled)
        left, top = round(at[0] * scale), round(at[1] * scale)
        frame[top:top + button.shape[0], left:left + button.shape[1]] = button
    return frame


def build_samples() -> List[ac.EvaluationSample]:
    """Five labelled frames: the cases a real locator meets."""
    template = draw_button()
    width, height = _TEMPLATE_SIZE

    def box(left: int, top: int, origin: Tuple[int, int] = (0, 0)) -> Tuple[int, int, int, int]:
        return (origin[0] + left, origin[1] + top,
                origin[0] + left + width, origin[1] + top + height)

    return [
        ac.EvaluationSample("plain", draw_frame((100, 60)), box(100, 60), template=template),
        # The same screen captured on a 150 % display: 1.5 frame pixels per unit.
        ac.EvaluationSample("hidpi-150", draw_frame((100, 60), scale=1.5), box(100, 60),
                            scale=1.5, template=template),
        # A monitor left of the primary: its top-left is at a negative x.
        ac.EvaluationSample("left-monitor", draw_frame((30, 120)), box(30, 120, (-320, 0)),
                            origin=(-320, 0), template=template),
        # The button is not on this screen at all: the right answer is a miss.
        ac.EvaluationSample("absent", draw_frame(None), expect_miss=True, template=template),
        # After a redesign the old template should not be "found" anywhere.
        ac.EvaluationSample("restyled", draw_frame((200, 40), restyled=True),
                            expect_miss=True, template=template),
    ]


def validate() -> int:
    """Score two template versions on the drawn frames and check the result."""
    comparison = ac.evaluate_locators(build_samples(), {
        "v1-single-scale": ac.template_match_strategy(threshold=0.9),
        "v2-multi-scale": ac.template_match_strategy(threshold=0.9, scales=(1.0, 1.5)),
    })
    print(format_comparison(comparison))
    gate = {"v2-multi-scale": {"min_accuracy": 1.0, "max_false_positive": 0.0}}
    violations = check_thresholds(comparison, gate)
    print("thresholds:", "met" if not violations else violations)

    old, new = comparison.report("v1-single-scale"), comparison.report("v2-multi-scale")
    problems = list(violations)
    if [row.sample_id for row in comparison.failures("v1-single-scale")] != ["hidpi-150"]:
        problems.append("v1 should fail exactly the HiDPI sample")
    if comparison.failures("v2-multi-scale"):
        problems.append("v2 should get every labelled sample right")
    if not (old.accuracy.value or 0) < (new.accuracy.value or 0):
        problems.append("v2 should be measurably more accurate than v1")
    for problem in problems:
        print(f"FAILED: {problem}")
    print("validate:", "failed" if problems else "ok")
    return 1 if problems else 0


def main(argv: Optional[List[str]] = None) -> int:
    """Parse the command line; see the module docstring."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--validate", action="store_true",
                        help="evaluate frames drawn in memory and check the scores")
    parser.add_argument("--dataset", help="a dataset JSON file to evaluate (offline)")
    args = parser.parse_args(argv)
    if args.dataset:
        report = ac.evaluate_healing_dataset(args.dataset)
        print(json.dumps({key: report[key] for key in ("versions", "violations", "passed")},
                         indent=2))
        return 0 if report["passed"] else 1
    if not args.validate:
        parser.error("use --validate, or name a dataset with --dataset")
    return validate()


if __name__ == "__main__":
    sys.exit(main())
