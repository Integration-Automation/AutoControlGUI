"""Which capability each REST route, MCP tool and ``AC_*`` command needs.

Three surfaces, one rule each:

* **REST routes** are listed one by one. A route missing from the list needs
  ``manage_hosts``, so a route added without a decision is admin-only rather
  than open.
* **MCP tools** follow their own annotation -- a tool marked read-only needs
  ``read_screen``, any other ``drive_input`` -- except the few named here
  that change how the host itself is exposed.
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
}

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
