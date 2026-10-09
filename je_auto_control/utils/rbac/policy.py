"""Which capability each REST route, MCP tool and ``AC_*`` command needs.

Three surfaces, one rule each:

* **REST routes** are listed one by one. A route missing from the list needs
  ``manage_hosts``, so a route added without a decision is admin-only rather
  than open. A ``GET`` route that returns records or configuration the host
  keeps needs ``read_data`` like the MCP tool reading the same thing; one
  that observes live state needs ``read_screen``.
* **MCP tools** follow their own annotation -- a tool marked read-only needs
  ``read_screen``, any other ``drive_input`` -- except the ones named here:
  those that change how the host itself is exposed, those that manage users,
  and the read-only tools that hand back the host's data rather than what is
  on its screen (``read_data``).
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
_USERS = Capability.MANAGE_USERS
_DATA = Capability.READ_DATA

REST_ROUTE_CAPABILITIES: Dict[Tuple[str, str], str] = {
    ("GET", "/metrics"): _READ,
    ("GET", "/jobs"): _READ,
    ("GET", "/history"): _DATA,  # run history, as ac_list_run_history
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
    ("GET", "/usb/acl"): _DATA,  # the stored ACL, as ac_usb_acl_list
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

#: The routes that need ``read_data``: the ones returning records or
#: configuration the host keeps, by the rule :data:`DATA_TOOLS` states. Each
#: has an MCP tool reading the same thing, and the two must agree.
DATA_ROUTES = frozenset(
    route for route, needed in REST_ROUTE_CAPABILITIES.items() if needed == _DATA)

#: Commands that need more than ``drive_input``. Every other command is
#: covered by the capability of the surface that submitted the action list.
COMMAND_CAPABILITIES: Dict[str, str] = {
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
    "AC_user_add": _USERS,
    "AC_user_remove": _USERS,
    "AC_user_set_role": _USERS,
    "AC_user_rotate_token": _USERS,
    "AC_user_list": _USERS,
}

#: Read-only MCP tools that expose data rather than screen state. "Read-only"
#: says a tool changes nothing; it does not say that what it returns is
#: something a viewer of the desktop was meant to see.
#:
#: The rule: a tool that returns records or configuration the host keeps --
#: history, traces, cost ledgers, healing logs, journals, saved libraries, ACL
#: contents -- is listed here; a tool that only observes the live screen (or
#: computes on what the caller sent) is not. What a tool costs to run is a
#: separate question this table does not answer: ``ac_vlm_locate`` and
#: ``ac_self_heal_locate`` read the screen and stay ``read_screen`` although a
#: call may be billed by a model provider.
DATA_TOOLS = frozenset({
    # the clipboard and its history, a connected device's included
    "ac_get_clipboard", "ac_get_clipboard_csv", "ac_get_clipboard_files",
    "ac_get_clipboard_html", "ac_get_clipboard_image", "ac_get_clipboard_rtf",
    "ac_clipboard_formats", "ac_assert_clipboard",
    "ac_clip_history_list", "ac_clip_history_search",
    "ac_android_get_clipboard", "ac_ios_get_clipboard",
    # records the host keeps of what ran: run history and what is derived
    # from it, agent traces, the cost ledger, action journals
    "ac_list_run_history", "ac_flaky_report", "ac_rank_tests", "ac_select_tests",
    "ac_shard_suite", "ac_trace_export", "ac_trace_summary",
    "ac_costs_list", "ac_costs_summary", "ac_journal_read", "ac_journal_runs",
    # the self-healing log, its statistics, stored revisions and datasets;
    # locator strategy history and repairs; saved locators and skills
    "ac_self_heal_log_list", "ac_heal_stats", "ac_self_heal_revision_list",
    "ac_self_heal_evaluate", "ac_ab_report", "ac_ab_best_strategy",
    "ac_repair_pending", "ac_repair_resolved", "ac_element_list",
    "ac_skill_list", "ac_skill_search",
    # stored policy and state: the USB ACL, lease tokens, quarantine,
    # artifacts awaiting approval, the recorded config-sync state
    "ac_usb_acl_list", "ac_lease_active", "ac_quarantine_list",
    "ac_pending_artifacts", "ac_config_sync_status",
    # files: their content, or an oracle on it (substring, digest)
    "ac_load_dotenv", "ac_load_data", "ac_read_action_file", "ac_read_document",
    "ac_read_presentation", "ac_read_workbook", "ac_extract_pdf_text",
    "ac_assert_pdf_text", "ac_assert_file", "ac_build_provenance",
    "ac_verify_provenance",
    # databases and the named stores kept on the host
    "ac_sql_query", "ac_assert_db", "ac_get_asset", "ac_list_assets",
    "ac_cas_get", "ac_outbox_pending", "ac_checkpoint_status",
    "ac_memory_recall", "ac_memory_recent", "ac_s3_list",
    # references into the environment, files and the secrets vault; tokens
    "ac_resolve_ref", "ac_resolve_refs", "ac_generate_otp",
    "ac_jwt_encode", "ac_jwt_decode",
    # the process list, the network as seen from the host, the microphone
    "ac_list_processes", "ac_assert_process", "ac_wait_for_process",
    "ac_assert_http", "ac_wait_for_port", "ac_assert_audio",
})

#: MCP tools whose capability is not the one their read-only hint implies.
TOOL_CAPABILITIES: Dict[str, str] = {
    "ac_remote_host_start": _HOSTS,
    "ac_remote_host_stop": _HOSTS,
    "ac_usb_acl_add": _HOSTS,
    "ac_usb_acl_remove": _HOSTS,
    "ac_usb_acl_set_default": _HOSTS,
    "ac_usb_passthrough_enable": _HOSTS,
    "ac_egress_allow": _HOSTS,
    "ac_egress_reset": _HOSTS,
    "ac_load_plugins": _HOSTS,
    "ac_user_add": _USERS,
    "ac_user_remove": _USERS,
    "ac_user_set_role": _USERS,
    "ac_user_rotate_token": _USERS,
    "ac_user_list": _USERS,
    **dict.fromkeys(DATA_TOOLS, _DATA),
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
    "COMMAND_CAPABILITIES", "DATA_ROUTES", "DATA_TOOLS", "REST_ROUTE_CAPABILITIES",
    "TOOL_CAPABILITIES",
    "authorize_command", "capability_for_command", "capability_for_route",
    "capability_for_tool", "denied_command_in",
]
