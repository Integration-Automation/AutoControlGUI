"""Self-healing locators: image-template first, VLM fallback.

Public surface:

* :func:`self_heal_locate` — return resolved screen coordinates or a
  miss outcome without raising;
* :func:`self_heal_click` — same, then click the resolved point, and record
  whether a caller-supplied check verified the click;
* :class:`HealOutcome` — structured result both helpers return;
* :data:`default_heal_log` — singleton JSON-lines log every heal
  attempt is appended to (override per-call via ``log=`` argument);
* :func:`heal_context` — stamp run / step / locator ids and a locator
  version on the events logged inside a block;
* :func:`evaluate_locators` / :func:`evaluate_healing_dataset` — score strategy
  versions against the same labelled frames (:mod:`evaluation`);
* :func:`propose_template_revision` and friends — candidate template
  revisions with preview, accept and revert (:mod:`template_revision`).
"""
from je_auto_control.utils.self_healing.eval_strategies import (
    EvaluationDataset, build_strategy, evaluate_healing_dataset,
    load_evaluation_dataset, template_match_strategy,
)
from je_auto_control.utils.self_healing.eval_vlm import vlm_strategy
from je_auto_control.utils.self_healing.evaluation import (
    EvaluationSample, HealingComparison, HealingEvaluationError,
    LocateRequest, LocatorStrategy, ModelUsage, Ratio, SampleResult, UsageMeter,
    VersionReport, check_thresholds, evaluate_locators, format_comparison,
)
from je_auto_control.utils.self_healing.heal_log import (
    HEAL_EVENT_SCHEMA_VERSION, HealEvent, HealEventLog, default_heal_log,
)
from je_auto_control.utils.self_healing.locator import (
    HealOutcome, SelfHealError,
    METHOD_IMAGE, METHOD_MISS, METHOD_VLM,
    heal_context, self_heal_click, self_heal_locate,
)
from je_auto_control.utils.self_healing.template_revision import (
    TemplateRevision, TemplateRevisionError, TemplateRevisionStore,
    accept_template_revision, default_template_revisions,
    list_template_revisions, preview_template_revision,
    propose_template_revision, revert_template_revision,
)


__all__ = [
    "EvaluationDataset", "EvaluationSample", "HEAL_EVENT_SCHEMA_VERSION",
    "HealEvent", "HealEventLog", "HealOutcome", "HealingComparison",
    "HealingEvaluationError", "LocateRequest", "LocatorStrategy",
    "METHOD_IMAGE", "METHOD_MISS", "METHOD_VLM", "ModelUsage",
    "Ratio", "SampleResult", "SelfHealError", "UsageMeter",
    "TemplateRevision", "TemplateRevisionError", "TemplateRevisionStore",
    "VersionReport",
    "accept_template_revision", "build_strategy", "check_thresholds",
    "default_heal_log", "default_template_revisions", "evaluate_healing_dataset",
    "evaluate_locators", "format_comparison", "heal_context",
    "list_template_revisions", "load_evaluation_dataset",
    "preview_template_revision", "propose_template_revision",
    "revert_template_revision", "self_heal_click", "self_heal_locate",
    "template_match_strategy", "vlm_strategy",
]
