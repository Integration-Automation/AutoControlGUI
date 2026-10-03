"""Beta fixed-frame locator comparison and reviewed template revision APIs."""
from je_auto_control.utils.self_healing import (
    EvaluationSample, HealingComparison, HealingEvaluationError, LocatorPrediction,
    LocatorStrategy, TemplateRevisionStore, accept_template_candidate, compare_healing_versions,
    create_template_candidate, evaluate_locators, healing_context, preview_template_candidate,
    revert_template_revision, validate_template_candidate,
)

__all__ = ['EvaluationSample', 'HealingComparison', 'HealingEvaluationError', 'LocatorPrediction',
           'LocatorStrategy', 'TemplateRevisionStore', 'accept_template_candidate', 'compare_healing_versions',
           'create_template_candidate', 'evaluate_locators', 'healing_context', 'preview_template_candidate',
           'revert_template_revision', 'validate_template_candidate']
