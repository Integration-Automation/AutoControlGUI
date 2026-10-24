"""Which capability each REST route, MCP tool and ``AC_*`` command needs.

Three surfaces, one rule each:

* **REST routes** are listed one by one. A route missing from the list needs
  ``manage_hosts``, so a route added without a decision is admin-only rather
  than open.
* **MCP tools** default to ``read_screen`` for a read-only annotation and
  ``drive_input`` otherwise. Named overrides separate non-mutating sensitive
  reads (clipboard, local data, credentials, network and audio) from screen
  observation, and protect administration of the host itself.
* **``AC_*`` commands** reach the executor through anything that runs an
  action list (``POST /execute``, ``ac_execute_actions``, an action file).
  Being allowed to run actions is ``drive_input``; the commands named here
  need more, and are checked both where the list is submitted and again by
  the executor, which is what covers a list read from a file.

The roles are not a sandbox. An operator drives the real keyboard and can
launch processes, so anything the desktop user could do by hand is within
reach. What the table protects is the host's own privileged state: its
signing key, its user and host administration, the servers it runs, its USB
and egress policy, its secrets vault and its audit log.
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, Optional, Tuple

from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, AuthorizationError, current_authorization,
)
from je_auto_control.utils.rbac.users import Capability

_READ = Capability.READ_SCREEN
_DRIVE = Capability.DRIVE_INPUT
_HOSTS = Capability.MANAGE_HOSTS
_AUDIT = Capability.READ_AUDIT

REST_ROUTE_CAPABILITIES: Dict[Tuple[str, str], str] = {
    ("POST", "/agent/target"): _HOSTS,
    ("GET", "/agent/targets"): _DRIVE,
    ("GET", "/agent/tasks"): _DRIVE,
    ("GET", "/agent/task"): _DRIVE,
    ("POST", "/agent/shutdown"): _HOSTS,
    ("POST", "/agent/recover_target"): _HOSTS,
    ("GET", "/metrics"): _READ,
    ("GET", "/jobs"): _READ,
    ("GET", "/history"): _READ,
    ("GET", "/screenshot"): _READ,
    ("GET", "/mouse_position"): _READ,
    ("GET", "/screen_size"): _READ,
    ("GET", "/windows"): _READ,
    ("GET", "/sessions"): _READ,
    ("GET", "/commands"): _READ,
    ("GET", "/inspector/recent"): _READ,
    ("GET", "/inspector/summary"): _READ,
    ("GET", "/usb/devices"): _READ,
    ("GET", "/usb/events"): _READ,
    ("GET", "/usb/passthrough/status"): _READ,
    ("GET", "/usb/acl"): _READ,
    ("GET", "/usb/loopback/devices"): _READ,
    ("GET", "/usb/remote/devices"): _READ,
    ("GET", "/diagnose"): _READ,
    ("GET", "/openapi.json"): _READ,
    ("GET", "/audit/list"): _AUDIT,
    ("GET", "/audit/verify"): _AUDIT,
    ("POST", "/execute"): _DRIVE,
    ("POST", "/execute_file"): _DRIVE,
    ("POST", "/usb/loopback/open"): _DRIVE,
    ("POST", "/usb/remote/open"): _DRIVE,
    ("POST", "/config/export"): _HOSTS,
    ("POST", "/config/import"): _HOSTS,
    ("POST", "/usb/passthrough/enable"): _HOSTS,
    ("POST", "/usb/acl/add"): _HOSTS,
    ("POST", "/usb/acl/remove"): _HOSTS,
    ("POST", "/usb/acl/default"): _HOSTS,
}
REST_ROUTE_CAPABILITIES.update({("POST", f"/agent/{operation}"): _DRIVE
                                for operation in ("submit", "observe", "act", "finish", "pause", "resume",
                                                  "cancel", "draft", "stop_all", "receipts", "reconcile",
                                                  "prune", "trigger", "skill", "lookup", "recovery", "dag")})

#: Commands that need more than ``drive_input``. Every other command is
#: covered by the capability of the surface that submitted the action list.
COMMAND_CAPABILITIES: Dict[str, str] = {
    "AC_agent_target": _HOSTS,
    "AC_agent_target_recover": _HOSTS,
    "AC_agent_runtime_stop": _HOSTS,
    "AC_agent_runtime_start": _HOSTS,
    "AC_probe_capabilities": _READ,
    "AC_diagnose": _READ,
    "AC_mcp_tool_search": _READ,
    "AC_mcp_tool_schema": _READ,
    "AC_history_capture": _DRIVE,
    "AC_self_heal_evaluate": _DRIVE,
    "AC_self_heal_run": _DRIVE,
    "AC_self_heal_source": _DRIVE,
    "AC_generate_candidate_from_log": _DRIVE,
    "AC_config_store_get": _DRIVE,
    "AC_config_store_commit": _DRIVE,
    "AC_config_causal_fetch": _DRIVE,
    "AC_config_causal_commit": _DRIVE,
    "AC_sync_outbox_flush": _DRIVE,
    "AC_sync_peer_control": _DRIVE,
    "AC_sync_asset_manifest": _DRIVE,
    "AC_sync_assets": _DRIVE,
    "AC_sync_adapter_snapshot": _DRIVE,
    "AC_sync_workspace": _DRIVE,
    "AC_sync_adapter_apply": _DRIVE,
    "AC_sync_adapter_resolve": _DRIVE,
    "AC_sync_profile_materialize": _DRIVE,
    "AC_sync_profile_load": _DRIVE,
    "AC_sync_entry_merge": _READ,
    "AC_sync_peer_state": _READ,
    "AC_sync_outbox_enqueue": _DRIVE,
    "AC_sync_outbox_status": _DRIVE,
    "AC_template_candidate_create": _DRIVE,
    "AC_template_candidate_preview": _DRIVE,
    "AC_template_candidate_verify": _DRIVE,
    "AC_template_candidate_accept": _DRIVE,
    "AC_template_candidate_revert": _DRIVE,
    "AC_journal_capture": _DRIVE,
    "AC_journal_read": _DRIVE,
    "AC_sign_action_file": Capability.SIGN_ACTIONS,
    "AC_audit_log_list": _AUDIT,
    "AC_audit_log_verify": _AUDIT,
    "AC_audit_log_clear": _HOSTS,
    "AC_admin_add_host": _HOSTS,
    "AC_admin_remove_host": _HOSTS,
    "AC_admin_list_hosts": _HOSTS,
    "AC_admin_poll": _HOSTS,
    "AC_admin_broadcast_execute": _HOSTS,
    "AC_rest_api_start": _HOSTS,
    "AC_rest_api_stop": _HOSTS,
    "AC_rest_api_status": _HOSTS,  # its reply carries the shared token
    "AC_start_mcp_server": _HOSTS,
    "AC_start_mcp_http_server": _HOSTS,
    "AC_start_remote_host": _HOSTS,
    "AC_stop_remote_host": _HOSTS,
    "AC_start_webrtc_host": _HOSTS,
    "AC_stop_webrtc_host": _HOSTS,
    "AC_start_ws_host": _HOSTS,
    "AC_stop_ws_host": _HOSTS,
    "AC_webhook_add": _HOSTS,
    "AC_webhook_remove": _HOSTS,
    "AC_webhook_start": _HOSTS,
    "AC_webhook_stop": _HOSTS,
    "AC_usb_acl_add": _HOSTS,
    "AC_usb_acl_remove": _HOSTS,
    "AC_usb_acl_set_default": _HOSTS,
    "AC_usb_acl_import": _HOSTS,
    "AC_usb_acl_export": _HOSTS,
    "AC_usb_passthrough_enable": _HOSTS,
    "AC_config_import": _HOSTS,
    "AC_config_export": _HOSTS,
    "AC_egress_allow": _HOSTS,
    "AC_egress_reset": _HOSTS,
    "AC_load_plugins": _HOSTS,
    "AC_add_package_to_executor": _HOSTS,
    "AC_add_package_to_callback_executor": _HOSTS,
    "AC_secret_init": _HOSTS,
    "AC_secret_set": _HOSTS,
    "AC_secret_remove": _HOSTS,
    "AC_secret_unlock": _HOSTS,
    "AC_secret_lock": _HOSTS,
}

#: MCP tools whose capability is not the one their read-only hint implies.
TOOL_CAPABILITIES: Dict[str, str] = {
    "ac_browser_link": _DRIVE,
    "ac_browser_wait": _DRIVE,
    "ac_browser_read": _DRIVE,
    "ac_agent_target": _HOSTS,
    "ac_agent_target_list": _DRIVE,
    "ac_workflow_wait": _DRIVE,
    "ac_agent_target_recover": _HOSTS,
    "ac_agent_runtime_stop": _HOSTS,
    "ac_agent_runtime_start": _HOSTS,
    "ac_agent_runtime_status": _DRIVE,
    "ac_agent_skill_list": _DRIVE,
    "ac_agent_task_get": _DRIVE,
    "ac_agent_task_lookup": _DRIVE,
    "ac_agent_dag_inspect": _DRIVE,
    "ac_agent_task_list": _DRIVE,
    "ac_agent_task_draft": _DRIVE,
    "ac_agent_task_receipts": _DRIVE,
    "ac_agent_task_recovery": _DRIVE,
    "ac_agent_trigger_list": _DRIVE,
    "ac_journal_capture": _DRIVE,
    "ac_journal_read": _DRIVE,
    "ac_remote_host_start": _HOSTS,
    "ac_remote_host_stop": _HOSTS,
    "ac_usb_acl_add": _HOSTS,
    "ac_usb_acl_remove": _HOSTS,
    "ac_usb_acl_set_default": _HOSTS,
    "ac_usb_passthrough_enable": _HOSTS,
    "ac_egress_allow": _HOSTS,
    "ac_egress_reset": _HOSTS,
    "ac_load_plugins": _HOSTS,
    # A non-mutating hint does not grant access to the desktop user's private
    # clipboard, files, credentials, network endpoints or microphone. Assertion
    # containers may invoke those same reads through their nested specs.
    "ac_get_clipboard": _DRIVE,
    "ac_get_clipboard_image": _DRIVE,
    "ac_get_clipboard_html": _DRIVE,
    "ac_get_clipboard_files": _DRIVE,
    "ac_get_clipboard_rtf": _DRIVE,
    "ac_get_clipboard_csv": _DRIVE,
    "ac_clipboard_formats": _DRIVE,
    "ac_clip_history_list": _DRIVE,
    "ac_clip_history_search": _DRIVE,
    "ac_assert_clipboard": _DRIVE,
    "ac_read_action_file": _DRIVE,
    "ac_load_dotenv": _DRIVE,
    "ac_sql_query": _DRIVE,
    "ac_assert_db": _DRIVE,
    "ac_read_workbook": _DRIVE,
    "ac_read_document": _DRIVE,
    "ac_read_presentation": _DRIVE,
    "ac_extract_pdf_text": _DRIVE,
    "ac_assert_pdf_text": _DRIVE,
    "ac_load_data": _DRIVE,
    "ac_assert_file": _DRIVE,
    "ac_resolve_ref": _DRIVE,
    "ac_resolve_refs": _DRIVE,
    "ac_jwt_encode": _DRIVE,
    "ac_generate_otp": _DRIVE,
    "ac_assert_http": _DRIVE,
    "ac_wait_for_port": _DRIVE,
    "ac_s3_list": _DRIVE,
    "ac_assert_all": _DRIVE,
    "ac_assert_any": _DRIVE,
    "ac_assert_eventually": _DRIVE,
    "ac_assert_audio": _DRIVE,
    "ac_get_asset": _DRIVE,
    "ac_list_assets": _DRIVE,
    "ac_cas_get": _DRIVE,
    "ac_outbox_pending": _DRIVE,
    "ac_checkpoint_status": _DRIVE,
    "ac_memory_recall": _DRIVE,
    "ac_memory_recent": _DRIVE,
    "ac_memory_stats": _DRIVE,
    "ac_queue_stats": _DRIVE,
    "ac_rank_tests": _DRIVE,
    "ac_select_tests": _DRIVE,
    "ac_shard_suite": _DRIVE,
    "ac_element_find": _DRIVE,
    "ac_element_list": _DRIVE,
    "ac_skill_list": _DRIVE,
    "ac_skill_search": _DRIVE,
    "ac_pending_artifacts": _DRIVE,
    "ac_approval_status": _DRIVE,
    "ac_repair_resolved": _DRIVE,
    "ac_repair_pending": _DRIVE,
    "ac_vlm_locate": _DRIVE,
    "ac_self_heal_locate": _DRIVE,
    "ac_self_heal_evaluate": _DRIVE,
    "ac_self_heal_run": _DRIVE,
    "ac_self_heal_source": _DRIVE,
    "ac_generate_candidate_from_log": _DRIVE,
    "ac_config_store_get": _DRIVE,
    "ac_config_store_commit": _DRIVE,
    "ac_config_causal_fetch": _DRIVE,
    "ac_config_causal_commit": _DRIVE,
    "ac_sync_outbox_flush": _DRIVE,
    "ac_sync_peer_control": _DRIVE,
    "ac_sync_asset_manifest": _DRIVE,
    "ac_sync_assets": _DRIVE,
    "ac_sync_adapter_snapshot": _DRIVE,
    "ac_sync_workspace": _DRIVE,
    "ac_sync_adapter_apply": _DRIVE,
    "ac_sync_adapter_resolve": _DRIVE,
    "ac_sync_profile_materialize": _DRIVE,
    "ac_sync_profile_load": _DRIVE,
    "ac_sync_entry_merge": _READ,
    "ac_sync_peer_state": _READ,
    "ac_sync_outbox_enqueue": _DRIVE,
    "ac_sync_outbox_status": _DRIVE,
    "ac_template_candidate_create": _DRIVE,
    "ac_template_candidate_preview": _DRIVE,
    "ac_template_candidate_verify": _DRIVE,
    "ac_template_candidate_accept": _DRIVE,
    "ac_template_candidate_revert": _DRIVE,
    "ac_describe_screen": _DRIVE,
}


def capability_for_route(method: str, path: str) -> str:
    """The capability ``method path`` needs; an unlisted route is admin-only."""
    return REST_ROUTE_CAPABILITIES.get((method.upper(), path), _HOSTS)


def capability_for_tool(name: str, read_only: bool) -> str:
    """The capability the MCP tool ``name`` needs, given its read-only hint."""
    listed = TOOL_CAPABILITIES.get(name)
    if listed is not None:
        return listed
    return _READ if read_only else _DRIVE


def capability_for_command(name: str) -> str:
    """The capability the ``AC_*`` command ``name`` needs."""
    return COMMAND_CAPABILITIES.get(name, _DRIVE)


def authorize_command(name: Any) -> None:
    """Refuse a privileged command the current caller's role does not grant.

    Called by the executor for every action. Outside an RBAC scope it does
    nothing, and inside one it only looks at the commands listed in
    :data:`COMMAND_CAPABILITIES` -- whether the caller may run actions at all
    was decided by the surface that accepted the request.
    """
    context = current_authorization()
    if context is None or not isinstance(name, str):
        return
    needed = COMMAND_CAPABILITIES.get(name)
    if needed is not None and not context.allows(needed):
        raise AuthorizationError(
            f"{name} needs the {needed!r} capability; user {context.user_id!r} "
            f"has role {context.role!r}", capability=needed)


def denied_command_in(payload: Any,
                      context: AuthorizationContext) -> Optional[Tuple[str, str]]:
    """``(command, capability)`` for the first privileged command ``context`` may not run.

    Walks ``payload`` -- a request body, a tool's arguments -- wherever an
    action list could be nested in it, so a request is refused whole before
    its first action runs rather than part-way through. A list that merely
    starts with a command's name is treated as that command: refusing a
    look-alike costs a retry, missing a real one is the failure.
    """
    for name in _leading_names(payload, depth=0):
        needed = COMMAND_CAPABILITIES.get(name)
        if needed is not None and not context.allows(needed):
            return name, needed
    return None


_MAX_WALK_DEPTH = 200


def _leading_names(node: Any, depth: int) -> Iterator[str]:
    """Yield the first item of every list in ``node`` that is a string."""
    if depth > _MAX_WALK_DEPTH:
        return
    if isinstance(node, dict):
        for value in node.values():
            yield from _leading_names(value, depth + 1)
        return
    if not isinstance(node, (list, tuple)):
        return
    if node and isinstance(node[0], str):
        yield node[0]
    for item in node:
        yield from _leading_names(item, depth + 1)


__all__ = [
    "COMMAND_CAPABILITIES", "REST_ROUTE_CAPABILITIES", "TOOL_CAPABILITIES",
    "authorize_command", "capability_for_command", "capability_for_route",
    "capability_for_tool", "denied_command_in",
]
