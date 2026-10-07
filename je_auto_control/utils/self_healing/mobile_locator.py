"""Self-heal on one device frame, preserving evidence and native-point coordinates."""
from __future__ import annotations

from time import monotonic
from typing import Callable, Optional, TYPE_CHECKING

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.self_healing.frame_strategies import TemplateFrameStrategy, VLMFrameStrategy
from je_auto_control.utils.self_healing.evaluation_models import LocatorStrategy
from je_auto_control.utils.self_healing.healing_context import record_frame
from je_auto_control.wrapper._mobile_models import DeviceSessionError
from je_auto_control.wrapper.device_frame import DeviceFrame

if TYPE_CHECKING:
    from je_auto_control.utils.self_healing.locator import HealOutcome


def locate_frame(frame: DeviceFrame, template: Optional[str], description: Optional[str],
                 threshold: float, model: Optional[str]) -> HealOutcome:
    """Try template then VLM against identical bytes; never recapture the desktop."""
    # pylint: disable-next=import-outside-toplevel  # reason: outcome compatibility without a locator import cycle
    from je_auto_control.utils.self_healing.locator import HealOutcome
    started = monotonic()
    errors: dict[str, str] = {}
    durations: dict[str, float] = {}
    strategies: list[tuple[str, Callable[[], LocatorStrategy]]] = []
    if template:
        strategies.append(('image', lambda: TemplateFrameStrategy(template, threshold)))
    if description:
        strategies.append(('vlm', lambda: VLMFrameStrategy(description, model)))
    for method, factory in strategies:
        durations[method] = monotonic()
        try:
            prediction = frame.locate(factory())
            record_frame(frame.png, method, backend=prediction.backend, model=prediction.model)
            durations[method] = (monotonic() - durations[method]) * 1000
            if prediction.coordinates is not None:
                point = frame.pixel_to_point(prediction.coordinates)
                return HealOutcome(True, (int(point[0]), int(point[1])), method,
                                   description, template, errors.get('image'),
                                   duration_ms=(monotonic() - started) * 1000,
                                   strategy_durations_ms=durations)
            errors[method] = 'no match on supplied device frame'
        except DeviceSessionError:
            raise
        except (AutoControlException, OSError, RuntimeError, ValueError, TypeError) as failure:
            errors[method] = repr(failure)
            durations[method] = (monotonic() - durations[method]) * 1000
    return HealOutcome(False, None, 'miss', description, template, errors.get('image'), errors.get('vlm'),
                       (monotonic() - started) * 1000, durations)
