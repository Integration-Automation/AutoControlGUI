"""Build the fixed self-healing evaluation samples from ``dataset.json``.

The frames are drawn here, from the descriptor, instead of being stored as
images: the descriptor is small enough to review in a diff, and a frame can be
regenerated bit for bit on any machine. Nothing in this module reads the
screen.

Every position in the descriptor is in *logical* units relative to the frame's
top-left corner. A sample's ``scale`` is frame pixels per logical unit, so a
target at ``[100, 60]`` on a ``scale: 1.5`` sample is drawn at frame pixel
``(150, 90)`` and 1.5 times the template's size — what a HiDPI capture of the
same screen looks like. ``origin`` is the screen coordinate of the frame's
top-left corner and may be negative (a monitor left of or above the primary).
"""
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from je_auto_control.utils.self_healing.evaluation import EvaluationSample

DATASET_PATH = Path(__file__).with_name("dataset.json")

STYLE_NORMAL = "normal"
STYLE_DECOY = "decoy"
STYLE_RESTYLED = "restyled"


def draw_element(width: int, height: int, style: str = STYLE_NORMAL) -> np.ndarray:
    """The target control as a ``height`` x ``width`` grayscale image.

    ``decoy`` is a neighbouring control that shares the frame and the label
    bar but not the icon; ``restyled`` is the same control after a redesign
    (inverted, different layout), which no version of the old template finds.
    """
    ramp = np.linspace(70, 190, width, dtype=np.float32)
    image = np.tile(ramp, (height, 1)).astype(np.uint8)
    cv2.rectangle(image, (0, 0), (width - 1, height - 1), 20, 2)
    if style == STYLE_RESTYLED:
        image = 255 - image
        cv2.line(image, (4, 4), (width - 5, height - 5), 0, 3)
        return image
    cv2.rectangle(image, (width // 2, height // 3),
                  (width - 7, height // 3 + 4), 240, -1)
    if style == STYLE_NORMAL:
        cv2.circle(image, (height // 2, height // 2), height // 4, 250, -1)
        cv2.rectangle(image, (width // 2, 2 * height // 3),
                      (width - 14, 2 * height // 3 + 3), 30, -1)
    else:
        cv2.rectangle(image, (6, height // 3), (height // 2 + 4, 2 * height // 3), 40, -1)
    return image


def _background(rng: np.random.Generator, width: int, height: int) -> np.ndarray:
    return rng.integers(105, 135, size=(height, width), dtype=np.uint8)


def _paste(frame: np.ndarray, element: np.ndarray, left: int, top: int) -> None:
    height, width = element.shape[:2]
    frame[top:top + height, left:left + width] = element


def _build_sample(entry: Dict[str, Any], template: np.ndarray,
                  rng: np.random.Generator) -> EvaluationSample:
    scale = float(entry.get("scale", 1.0))
    origin = tuple(entry.get("origin", (0, 0)))
    frame_width, frame_height = entry["frame_size"]
    frame = _background(rng, frame_width, frame_height)
    base_height, base_width = template.shape[:2]
    boxes: List[Tuple[int, int, int, int]] = []
    for target in entry.get("targets", ()):
        at_x, at_y = target["at"]
        element = draw_element(base_width, base_height, target.get("style", STYLE_NORMAL))
        if not math.isclose(scale, 1.0):
            # INTER_AREA / INTER_CUBIC on purpose: the strategy under test
            # resizes with INTER_LINEAR, so a scaled match is close, not exact.
            element = cv2.resize(element, None, fx=scale, fy=scale,
                                 interpolation=cv2.INTER_CUBIC)
        _paste(frame, element, int(round(at_x * scale)), int(round(at_y * scale)))
        boxes.append((origin[0] + at_x, origin[1] + at_y,
                      origin[0] + at_x + base_width, origin[1] + at_y + base_height))
    expected: Optional[int] = entry.get("expected_target")
    frame.setflags(write=False)
    return EvaluationSample(
        sample_id=entry["id"], frame=frame,
        expected_box=None if expected is None else boxes[expected],
        origin=origin, scale=scale, region=entry.get("region"),
        expect_miss=bool(entry.get("expect_miss", False)),
        template=template, description=entry.get("description"))


def load_descriptor(path: Path = DATASET_PATH) -> Dict[str, Any]:
    """The dataset descriptor as parsed JSON."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_samples(descriptor: Optional[Dict[str, Any]] = None) -> List[EvaluationSample]:
    """Every sample of the fixed dataset, drawn deterministically."""
    data = load_descriptor() if descriptor is None else descriptor
    width, height = data["template_size"]
    template = draw_element(width, height)
    template.setflags(write=False)
    rng = np.random.default_rng(int(data["seed"]))
    return [_build_sample(entry, template, rng) for entry in data["samples"]]
