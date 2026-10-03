"""Fixed-frame comparison and explicit candidate revision tools."""
from typing import List

from je_auto_control.utils.mcp_server.tools._base import DESTRUCTIVE, MCPTool, MCPToolAnnotations, READ_ONLY, schema
from je_auto_control.utils.self_healing.evaluation_api import (
    accept_template_candidate, compare_healing_versions, create_template_candidate,
    preview_template_candidate, revert_template_revision, validate_template_candidate,
)


def healing_evaluation_tools() -> List[MCPTool]:
    """Expose dataset comparison and reviewed revisions with conservative behavior hints."""
    text = {'type': 'string'}
    revision = {'store_path': text, 'revision_id': text}
    updates = MCPToolAnnotations(destructive=False, idempotent=False)
    return [
        MCPTool('ac_compare_healing_versions', 'Compare locator versions on a fixed labelled dataset; export reports.',
                schema({'dataset_path': text, 'versions': {'type': ['object', 'string']}, 'report_path': text},
                       required=['dataset_path', 'versions']), compare_healing_versions, updates),
        MCPTool('ac_create_template_candidate', 'Snapshot a proposed template without applying it.',
                schema({'store_path': text, 'template_path': text, 'candidate_path': text},
                       required=['store_path', 'template_path', 'candidate_path']), create_template_candidate, updates),
        MCPTool('ac_preview_template_candidate', 'Read checked base/candidate previews and validation evidence.',
                schema(revision, required=list(revision)), preview_template_candidate, READ_ONLY),
        MCPTool('ac_validate_template_candidate', 'Persist a fixed-frame candidate/base comparison with strict labels.',
                schema({**revision, 'dataset_path': text, 'threshold': {'type': 'number'}},
                       required=[*revision, 'dataset_path']), validate_template_candidate, updates),
        MCPTool('ac_accept_template_candidate', 'Apply a validated candidate if its baseline is unchanged.',
                schema(revision, required=list(revision)), accept_template_candidate, DESTRUCTIVE),
        MCPTool('ac_revert_template_revision', 'Restore a saved baseline if its accepted candidate is still current.',
                schema(revision, required=list(revision)), revert_template_revision, DESTRUCTIVE),
    ]
