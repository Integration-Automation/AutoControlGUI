"""Template and VLM strategies that consume an already captured immutable frame."""
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import ClassVar, Optional

from je_auto_control.utils.cv2_utils.optional import require_cv2
from je_auto_control.utils.cv2_utils.template_detection import _match_frame, _SCORE_EPSILON
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.path_guard.policy import scoped_path
from je_auto_control.utils.self_healing.evaluation_models import (
    EvaluationSample, HealingEvaluationError, LocatorPrediction, LocatorStrategy,
)
from je_auto_control.utils.vision.backends.base import VLMBackend, VLMNotAvailableError
from je_auto_control.utils.vision.backends import get_backend


@dataclass(frozen=True)
class TemplateFrameStrategy:
    """Match a root-checked template against supplied bytes without a screenshot."""
    template_path: str
    threshold: float = 0.9
    method: ClassVar[str] = 'image'

    def __post_init__(self) -> None:
        if not math.isfinite(self.threshold) or not 0 <= self.threshold <= 1:
            raise HealingEvaluationError('template threshold must be finite and within [0, 1]')
        if not self.template_path:
            raise HealingEvaluationError('template_path must be nonempty')
        scoped_path(self.template_path, operation='read')

    def locate(self, sample: EvaluationSample) -> LocatorPrediction:
        """Return the best frame-pixel match, or an image-strategy miss."""
        # pylint: disable-next=import-outside-toplevel  # reason: Pillow is loaded only for image evaluation
        from PIL import Image
        cv2 = require_cv2()
        path = scoped_path(self.template_path, operation='read')
        with Image.open(io.BytesIO(sample.frame)) as frame:
            _, scores, template = _match_frame(frame.convert('RGB'), str(path), cv2)
        if float(template.std()) < 1e-8:
            raise HealingEvaluationError('constant templates do not identify a target')
        # pylint: disable-next=no-member  # reason: minMaxLoc is provided by OpenCV's native bindings
        _, score, _, position = cv2.minMaxLoc(scores)
        if score < min(self.threshold, 1 - _SCORE_EPSILON):
            return LocatorPrediction(None, 'image')
        height, width = template.shape[:2]
        return LocatorPrediction((int(position[0]) + int(width) // 2,
                                  int(position[1]) + int(height) // 2), 'image', backend='opencv')


@dataclass(frozen=True)
class VLMFrameStrategy:
    """Send the supplied frame to a chosen backend, preserving its pixel coordinates."""
    description: str
    model: Optional[str] = None
    backend: Optional[VLMBackend] = None
    method: ClassVar[str] = 'vlm'

    def locate(self, sample: EvaluationSample) -> LocatorPrediction:
        """Ask the model about existing frame bytes; never recapture or click."""
        if not self.description.strip():
            raise HealingEvaluationError('VLM description must be nonempty')
        backend = self.backend if self.backend is not None else get_backend()
        if not backend.available:
            raise VLMNotAvailableError('no VLM backend configured for frame comparison')
        point = backend.locate(sample.frame, self.description, model=self.model)
        return LocatorPrediction(point, 'vlm', backend=backend.name, model=self.model)


@dataclass(frozen=True)
class FallbackFrameStrategy:
    """Try the template and then VLM on exactly the same immutable sample."""
    image: LocatorStrategy
    vlm: LocatorStrategy
    method: ClassVar[str] = 'vlm'

    def locate(self, sample: EvaluationSample) -> LocatorPrediction:
        """Return an image hit or the fallback result on the shared frame."""
        try:
            result = self.image.locate(sample)
        except (AutoControlException, OSError, RuntimeError, ValueError, TypeError):
            return self.vlm.locate(sample)
        return result if result.coordinates is not None else self.vlm.locate(sample)
