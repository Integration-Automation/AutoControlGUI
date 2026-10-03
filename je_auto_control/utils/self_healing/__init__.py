"""Self-healing locators, fixed-frame comparisons and reviewed template revisions.

Public surface:

* :func:`self_heal_locate` — return resolved screen coordinates or a
  miss outcome without raising;
* :func:`self_heal_click` — same, then click the resolved point;
* :class:`HealOutcome` — structured result both helpers return;
* :data:`default_heal_log` — singleton JSON-lines log every heal
  attempt is appended to (override per-call via ``log=`` argument).
"""
from je_auto_control.utils.self_healing.heal_log import (
    HealEvent, HealEventLog, default_heal_log,
)
from je_auto_control.utils.self_healing.locator import (
    HealOutcome, SelfHealError,
    METHOD_IMAGE, METHOD_MISS, METHOD_VLM,
    self_heal_click, self_heal_locate,
)
from je_auto_control.utils.self_healing.evaluation import (
    EvaluationSample, HealingComparison, HealingEvaluationError, LocatorPrediction,
    LocatorStrategy, evaluate_locators,
)
from je_auto_control.utils.self_healing.healing_context import healing_context
from je_auto_control.utils.self_healing.template_revisions import TemplateRevisionStore
from je_auto_control.utils.self_healing.evaluation_api import (
    accept_template_candidate, compare_healing_versions, create_template_candidate,
    preview_template_candidate, revert_template_revision, validate_template_candidate,
)


__all__ = [
    "HealEvent", "HealEventLog", "HealOutcome", "SelfHealError",
    "METHOD_IMAGE", "METHOD_MISS", "METHOD_VLM",
    "default_heal_log", "self_heal_click", "self_heal_locate",
    "EvaluationSample", "HealingComparison", "HealingEvaluationError", "LocatorPrediction",
    "LocatorStrategy", "evaluate_locators", "healing_context", "TemplateRevisionStore",
    "accept_template_candidate", "compare_healing_versions", "create_template_candidate",
    "preview_template_candidate", "revert_template_revision", "validate_template_candidate",
]
