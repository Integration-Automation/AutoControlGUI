"""JSON adapters for comparable healing versions and reviewed template revisions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Mapping, Optional, Union

from je_auto_control.utils.action_journal.events import JSONValue
from je_auto_control.utils.self_healing.evaluation import evaluate_locators
from je_auto_control.utils.self_healing.evaluation_dataset import (
    json_object, load_evaluation_dataset, write_comparison_report,
)
from je_auto_control.utils.self_healing.evaluation_models import HealingEvaluationError, LocatorStrategy
from je_auto_control.utils.self_healing.frame_strategies import (
    FallbackFrameStrategy, TemplateFrameStrategy, VLMFrameStrategy,
)
from je_auto_control.utils.self_healing.template_revisions import TemplateRevisionStore

VersionConfig = Union[Mapping[str, JSONValue], str]


def _config(versions: VersionConfig) -> Dict[str, JSONValue]:
    if isinstance(versions, str):
        try:
            return json_object(json.loads(versions))
        except json.JSONDecodeError as error:
            raise HealingEvaluationError('versions must be valid JSON') from error
    return json_object(dict(versions))


def _optional_text(config: Dict[str, JSONValue], key: str) -> Optional[str]:
    value = config.get(key)
    if value is not None and not isinstance(value, str):
        raise HealingEvaluationError(key + ' must be text')
    return value


def _strategy(value: JSONValue) -> LocatorStrategy:
    config = json_object(value)
    template, description, model = (_optional_text(config, key) for key in ('template_path', 'description', 'model'))
    threshold = config.get('threshold', 0.99)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise HealingEvaluationError('threshold must be numeric')
    if template and description:
        return FallbackFrameStrategy(TemplateFrameStrategy(template, threshold), VLMFrameStrategy(description, model))
    if template:
        return TemplateFrameStrategy(template, threshold)
    if description:
        return VLMFrameStrategy(description, model)
    raise HealingEvaluationError('each version needs a template_path or VLM description')


def compare_healing_versions(dataset_path: str, versions: Union[Mapping[str, JSONValue], str], *,
                             report_path: Optional[str] = None) -> Dict[str, JSONValue]:
    """Compare supplied version configurations on a fixed dataset, with optional JSON/HTML export."""
    strategies = {name: _strategy(value) for name, value in _config(versions).items()}
    report = evaluate_locators(load_evaluation_dataset(dataset_path), strategies).to_dict()
    report['dataset_path'] = str(Path(dataset_path).resolve())
    if report_path is not None:
        write_comparison_report(report, report_path)
    return report


def create_template_candidate(store_path: str, template_path: str, candidate_path: str) -> Dict[str, JSONValue]:
    """Snapshot a proposal and its baseline, preserving the current template."""
    store = TemplateRevisionStore(store_path)
    return store.preview(store.propose(Path(template_path), Path(candidate_path)))


def preview_template_candidate(store_path: str, revision_id: str) -> Dict[str, JSONValue]:
    """Read checked candidate/base identities and preview paths without writing files."""
    return TemplateRevisionStore(store_path).preview(revision_id)


def validate_template_candidate(store_path: str, revision_id: str, dataset_path: str,
                                threshold: float = 0.99) -> Dict[str, JSONValue]:
    """Persist a labelled base/candidate comparison; accept requires perfect labelled accuracy and a positive hit."""
    return TemplateRevisionStore(store_path).validate(
        revision_id, load_evaluation_dataset(dataset_path), threshold).to_dict()


def accept_template_candidate(store_path: str, revision_id: str) -> Dict[str, JSONValue]:
    """Apply a validated candidate with an unchanged-baseline check."""
    return TemplateRevisionStore(store_path).accept(revision_id)


def revert_template_revision(store_path: str, revision_id: str) -> Dict[str, JSONValue]:
    """Restore the saved baseline if the accepted candidate is still current."""
    return TemplateRevisionStore(store_path).revert(revision_id)
