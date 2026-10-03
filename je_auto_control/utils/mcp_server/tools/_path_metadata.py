"""Reviewed filesystem semantics; names such as JSONPath are never inferred."""
import os
from copy import deepcopy
from dataclasses import replace
from typing import Any, Dict

from je_auto_control.utils.mcp_server.tools._base import MCPTool
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError

# Each row was checked against its handler. Dot paths descend through objects;
# '*' addresses array items / mapping values. Mixed string/action-list 'source'
# is validated only when it is a string. Optional omitted fields stay omitted.
_READ_FIELDS = {
    'ac_generate_journal_candidate': 'journal_path',
    'ac_compare_healing_versions': 'dataset_path versions.*.template_path',
    'ac_create_template_candidate': 'template_path candidate_path',
    'ac_preview_template_candidate': 'store_path',
    'ac_validate_template_candidate': 'dataset_path',
    'ac_read_action_journal': 'path',
    'ac_list_journal_runs': 'path',
    'ac_read_file_to_var': 'path',
    'ac_pdf_to_var': 'path',
    'ac_sql_to_var': 'database',
    'ac_for_each_row': 'source.path',
    'ac_if_image_found': 'image',
    'ac_while_image': 'image',
    'ac_wait_image': 'image',
    'ac_clipboard_set_image': 'path',
    'ac_plan_file_drop': 'paths.*',
    'ac_perceptual_diff': 'actual expected',
    'ac_encrypt_action_file': 'path',
    'ac_decrypt_action_file': 'enc_path',
    'ac_usb_acl_import': 'path',
    'ac_sign_action_file': 'path private_key_path',
    'ac_verify_action_file': 'path public_key_path',
    'ac_wait_for_image': 'image_path',
    'ac_diff_screenshots': 'image_path_a image_path_b',
    'ac_self_heal_locate': 'template_path',
    'ac_self_heal_click': 'template_path',
    'ac_locate_image_center': 'image_path',
    'ac_locate_and_click': 'image_path',
    'ac_set_clipboard_image': 'image_path',
    'ac_execute_action_file': 'file_path',
    'ac_read_action_file': 'file_path',
    'ac_anchor_locate': 'anchor.template_path target.template_path',
    'ac_anchor_locate_all': 'anchor.template_path target.template_path',
    'ac_anchor_click': 'anchor.template_path target.template_path',
    'ac_wait_image_gone': 'image',
    'ac_wait_for_file': 'path',
    'ac_run_dag': 'definition.nodes.*.action_file',
    'ac_redact_screenshot': 'file_path',
    'ac_scheduler_add_job': 'script_path',
    'ac_trigger_add': 'script_path image_path watch_path',
    'ac_hotkey_bind': 'script_path',
    'ac_element_find': 'path',
    'ac_element_click': 'path',
    'ac_element_list': 'path',
    'ac_skill_run': 'path',
    'ac_skill_list': 'path',
    'ac_skill_search': 'path',
    'ac_read_workbook': 'path',
    'ac_read_document': 'path',
    'ac_read_presentation': 'path',
    'ac_chatops_dispatch': 'script_root',
    'ac_rank_tests': 'history_path',
    'ac_select_tests': 'history_path',
    'ac_shard_suite': 'history_path',
    'ac_match_ensemble': 'templates.*',
    'ac_observe_add': 'image',
    'ac_preprocess_image': 'source',
    'ac_set_clipboard_files': 'paths.*',
    'ac_drop_files': 'paths.*',
    'ac_image_histogram': 'source',
    'ac_image_quality': 'source',
    'ac_quality_gate': 'source',
    'ac_detect_scale': 'template haystack',
    'ac_scale_sweep': 'template haystack',
    'ac_salient_regions': 'source',
    'ac_most_salient': 'source',
    'ac_classify_icon': 'source',
    'ac_read_barcodes': 'source',
    'ac_pending_artifacts': 'approvals_dir',
    'ac_write_step_video': 'steps.*.image',
    'ac_s3_upload': 'local_path',
    'ac_image_hash': 'path',
    'ac_dedupe_images': 'paths.*',
    'ac_build_provenance': 'paths.*',
    'ac_verify_provenance': 'files.*',
    'ac_load_dotenv': 'path',
    'ac_launch_process': 'working_directory',
    'ac_assert_file': 'path',
    'ac_assert_image': 'template_path',
    'ac_assert_all': 'specs.*.template_path specs.*.path specs.*.database',
    'ac_assert_any': 'specs.*.template_path specs.*.path specs.*.database',
    'ac_assert_eventually': 'spec.template_path spec.path spec.database',
    'ac_load_data': 'source.path',
    'ac_sql_query': 'database',
    'ac_assert_db': 'database',
    'ac_send_email': 'message.attachments.*',
    'ac_extract_pdf_text': 'path',
    'ac_assert_pdf_text': 'path',
    'ac_assert_visual': 'golden_path',
    'ac_generate_code': 'source',
    'ac_assert_video_changes': 'video_path',
}
_WRITE_FIELDS = {
    'ac_generate_journal_candidate': 'output_path',
    'ac_compare_healing_versions': 'report_path',
    'ac_create_template_candidate': 'store_path',
    'ac_validate_template_candidate': 'store_path',
    'ac_accept_template_candidate': 'store_path',
    'ac_revert_template_revision': 'store_path',
    'ac_execute_journaled': 'path',
    'ac_clipboard_get_image': 'path',
    'ac_encrypt_action_file': 'path',
    'ac_decrypt_action_file': 'output_path',
    'ac_android_screenshot': 'file_path',
    'ac_usb_acl_export': 'path',
    'ac_annotate_screenshot': 'output_path',
    'ac_move_to_trash': 'path',
    'ac_capture_window': 'output_path',
    'ac_save_window_layout': 'path',
    'ac_create_signing_keypair': 'private_path public_path',
    'ac_screenshot': 'file_path',
    'ac_sign_action_file': 'path',
    'ac_write_action_file': 'file_path',
    'ac_redact_screenshot': 'output_path',
    'ac_ios_screenshot': 'file_path',
    'ac_web_screenshot': 'file_path',
    'ac_handle_file_dialog': 'path',
    'ac_generate_data': 'path',
    'ac_mcp_manifest': 'path',
    'ac_element_save': 'path',
    'ac_element_remove': 'path',
    'ac_skill_save': 'path',
    'ac_skill_remove': 'path',
    'ac_agent_card': 'path',
    'ac_write_workbook': 'path',
    'ac_write_document': 'path',
    'ac_write_presentation': 'path',
    'ac_generate_sbom': 'path',
    'ac_generate_sop': 'path',
    'ac_mark_screen': 'render_path',
    'ac_preprocess_image': 'output_path',
    'ac_verify_artifact': 'approvals_dir',
    'ac_approve_artifact': 'approvals_dir',
    'ac_compliance_report': 'path',
    'ac_write_step_video': 'output',
    'ac_s3_download': 'local_path',
    'ac_export_sarif': 'path',
    'ac_screen_record_start': 'file_path',
    'ac_take_golden': 'path',
    'ac_assert_visual': 'diff_path',
    'ac_generate_code': 'output',
    'ac_run_suite': 'junit_path allure_dir',
}
_DATABASE_TOOLS = '''queue_add queue_next queue_complete queue_fail queue_stats
memory_remember memory_recall memory_recent memory_forget memory_stats
run_resumable checkpoint_status checkpoint_clear approval_request approval_approve
approval_reject approval_status set_asset get_asset list_assets repair_record
repair_resolved repair_pending repair_approve'''.split()
_TEMPLATE_TOOLS = '''match_template match_template_all match_masked match_masked_all
match_rotated match_rotated_all match_with_trust auto_threshold match_auto edge_match
edge_match_all match_subpixel match_color match_color_all match_persistence feature_match
wait_actionable match_theme'''.split()
for _name in _DATABASE_TOOLS:
    _READ_FIELDS['ac_' + _name] = 'db'
for _name in '''queue_add queue_next queue_complete queue_fail memory_remember
memory_forget run_resumable checkpoint_clear approval_request approval_approve
approval_reject set_asset repair_record repair_approve'''.split():
    _WRITE_FIELDS['ac_' + _name] = 'db'
for _name in _TEMPLATE_TOOLS:
    _READ_FIELDS['ac_' + _name] = 'template'
_READ_FIELDS['ac_match_masked'] += ' mask'
_READ_FIELDS['ac_match_masked_all'] += ' mask'


def _mark(node: Dict[str, Any], components: list[str], operation: str) -> None:
    if not components:
        node.update({'format': 'path', 'x-autocontrol-operation': operation})
        return
    key, *rest = components
    if key == '*':
        child = node.setdefault('items', {})
        if node.get('type') != 'array':
            node.setdefault('additionalProperties', child)
    else:
        child = node.setdefault('properties', {}).setdefault(key, {})
    if isinstance(child, dict):
        _mark(child, rest, operation)


def annotate_file_fields(tool: MCPTool) -> MCPTool:
    """Attach reviewed semantic metadata to a registry descriptor copy."""
    annotated = deepcopy(tool.input_schema)
    for operation, fields in [('read', _READ_FIELDS), ('write', _WRITE_FIELDS)]:
        for field in fields.get(tool.name, '').split():
            _mark(annotated, field.split('.'), operation)
    if tool.name == 'ac_act_in_view':
        annotated['properties']['target'].update({
            'format': 'path', 'x-autocontrol-when': {'kind': 'image'},
        })
    if tool.name == 'ac_open_path':
        annotated['properties']['target']['format'] = 'path-or-url'
    return replace(tool, input_schema=annotated)


def _validate_location(value: str, node: Dict[str, Any], policy: PathPolicy) -> str:
    if node.get('format') == 'path-or-url' and '://' in value:
        if not value.startswith('file://'):
            return value
        from je_auto_control.utils.mcp_server._protocol import _file_uri_to_path
        local = _file_uri_to_path(value)
        if local is None:
            raise PathNotAllowedError('file URL must name a local path')
        value = local
    return str(policy.validate(value, operation=node.get('x-autocontrol-operation', 'read')))


def _field_schema(key: str, node: Dict[str, Any], arguments: Dict[str, Any]) -> Dict[str, Any]:
    properties = node.get('properties', {})
    child = properties.get(key, node.get('additionalProperties', {}))
    if not isinstance(child, dict):
        return {}
    condition = child.get('x-autocontrol-when', {})
    if any(arguments.get(name, expected) != expected for name, expected in condition.items()):
        return {}
    return child


def validate_path_arguments(value: Any, node: Dict[str, Any], policy: PathPolicy) -> Any:
    """Normalize only annotated filesystem values, including nested containers."""
    if not isinstance(node, dict):
        return value
    if node.get('format') in {'path', 'path-or-url'} and isinstance(value, (str, os.PathLike)):
        return _validate_location(os.fspath(value), node, policy)
    if isinstance(value, dict):
        return {key: validate_path_arguments(item, _field_schema(key, node, value), policy)
                for key, item in value.items()}
    if isinstance(value, list):
        return [validate_path_arguments(item, node.get('items', {}), policy) for item in value]
    return value
