"""Self-healing locators: image-template first, VLM fallback.

Public surface:

* :func:`self_heal_locate` — return resolved screen coordinates or a
  miss outcome without raising;
* :func:`self_heal_click` — same, then click the resolved point;
* :class:`HealOutcome` — structured result both helpers return;
* :data:`default_heal_log` — singleton JSON-lines log every heal
  attempt is appended to (override per-call via ``log=`` argument).
* :func:`evaluate_locators` — compare explicit strategies on fixed PNG samples;
  :func:`evaluate_healing_manifest` and :func:`write_healing_report` share local reports.
"""
from je_auto_control.utils.self_healing.heal_log import (
    HealEvent, HealEventLog, default_heal_log,
)
from je_auto_control.utils.self_healing.locator import (
    HealOutcome, SelfHealError,
    METHOD_IMAGE, METHOD_MISS, METHOD_VLM,
    self_heal_click, self_heal_locate,
)
from je_auto_control.utils.self_healing.evaluation import HealingComparison, evaluate_locators
from je_auto_control.utils.self_healing.evaluation_models import (
    EvaluationRatio, EvaluationSample, HealingAttempt, HealingEvaluationError,
    HealingVersionReport, LocatorCandidate, LocatorStrategy,
)
from je_auto_control.utils.self_healing.frame_locators import TemplateFrameLocator, VLMFrameLocator
from je_auto_control.utils.self_healing.evaluation_io import evaluate_healing_manifest, write_healing_report


__all__ = [
    "HealEvent", "HealEventLog", "HealOutcome", "SelfHealError",
    "METHOD_IMAGE", "METHOD_MISS", "METHOD_VLM",
    "default_heal_log", "self_heal_click", "self_heal_locate",
    "EvaluationRatio", "EvaluationSample", "HealingAttempt", "HealingComparison", "HealingEvaluationError",
    "HealingVersionReport", "LocatorCandidate", "LocatorStrategy", "TemplateFrameLocator", "VLMFrameLocator",
    "evaluate_healing_manifest", "evaluate_locators", "write_healing_report",
]
