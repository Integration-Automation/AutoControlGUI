"""Request identities and capability guards shared by remote entry points."""
from __future__ import annotations

import contextlib
import contextvars
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, Optional

from je_auto_control.utils.rbac.users import (
    Capability, UserAuthError, UserStore, can,
)


@dataclass(frozen=True)
class AuthorizationContext:
    """Authenticated user and role for one remote request."""
    user_id: str
    role: str


class AuthorizationError(UserAuthError):
    """An authenticated user lacks a required capability."""


_CURRENT: contextvars.ContextVar[Optional[AuthorizationContext]] = contextvars.ContextVar(
    'autocontrol_authorization', default=None)
_STORES: Dict[Path, UserStore] = {}
_STORES_LOCK = threading.Lock()


def configured_user_store() -> Optional[UserStore]:
    """Resolve the explicitly configured store, shared by servers and local GUI.

    Absent ``JE_AUTOCONTROL_USERS`` retains legacy authentication. A configured
    empty/unreadable store never falls back to a shared token.
    """
    path = os.environ.get('JE_AUTOCONTROL_USERS')
    if path is None:
        return None
    if not path.strip():
        raise UserAuthError('JE_AUTOCONTROL_USERS must name a users JSON file')
    resolved = Path(path).expanduser().resolve()
    with _STORES_LOCK:
        store = _STORES.get(resolved)
        if store is None:
            store = UserStore(resolved)
            _STORES[resolved] = store
        return store


def authenticate_header(header: Optional[str], store: UserStore) -> AuthorizationContext:
    """Authenticate a bearer token against the configured user store."""
    scheme, _, token = (header or '').strip().partition(' ')
    if scheme.lower() != 'bearer' or not token.strip():
        raise UserAuthError('bearer token required')
    record = store.authenticate(token.strip())
    return AuthorizationContext(record.user_id, record.role)


def current_authorization() -> Optional[AuthorizationContext]:
    """Current request identity; ``None`` for unrestricted local/legacy calls."""
    return _CURRENT.get()


@contextlib.contextmanager
def authorization_scope(context: Optional[AuthorizationContext]) -> Iterator[None]:
    """Bind a request identity and restore it on all exit paths."""
    token = _CURRENT.set(context)
    try:
        yield
    finally:
        _CURRENT.reset(token)


_ADMIN_PREFIXES = (
    'sign_', 'create_signing_', 'encrypt_', 'decrypt_', 'secret_', 'secrets_',
    'shell_', 'python_', 'plugin_', 'package_', 'host_', 'server_', 'rest_',
    'usb_', 'usbip_', 'remote_desktop_', 'file_', 'write_file', 'read_file',
    'config_', 'sync_', 'process_', 'subprocess_', 'keyring_', 'cert_', 'ssh_',
    'schedule_', 'scheduler_', 'trigger_', 'email_trigger_', 'watchdog_',
    'webhook_', 'pipeline_', 'failure_hook_', 'webrtc_',
    'admin_', 'add_package_', 'load_plugins', 'start_mcp_', 'start_remote_',
    'start_ws_', 'start_webrtc_', 'stop_remote_', 'stop_ws_', 'stop_webrtc_',
    'web_', 'http_', 's3_', 'write_document', 'write_presentation', 'write_workbook',
    'element_save', 'skill_save', 'skill_remove', 'notify_webhook',
)
_USER_PREFIXES = ('user_', 'users_', 'rbac_')
_AUDIT_PREFIXES = ('audit_', 'history_', 'logs_', 'log_')
_ADMIN_NAMES = frozenset({'shell', 'exec', 'eval', 'execute_python', 'run_python',
                          'open_path', 'install', 'uninstall', 'restart', 'shutdown',
                          'execute_process', 'android_shell', 'load_dotenv',
                          'add_package_to_callback_executor', 'parallel', 'run_dag',
                          'run_agent',
                          'lease_secret', 'scan_secrets', 'sign', 'encrypt', 'decrypt'})
_READ_COMMANDS = frozenset({'screen_size', 'get_screen_size', 'get_mouse_position',
                            'get_pixel', 'screenshot', 'a11y_list', 'a11y_find',
                            'list_windows', 'known_commands'})


def required_capability(name: str, *, read_only: bool = False) -> str:
    """Server-owned capability classification for tools and executor commands.

    Sensitive namespaces always require admin capabilities, even if a tool
    advertises read-only behavior. Unclassified mutating commands require input
    privileges; provider-defined read-only tools grant only observation.
    """
    normalized = name.lower()
    if normalized.startswith('ac_'):
        normalized = normalized[3:]
    if normalized.startswith(_USER_PREFIXES):
        return Capability.MANAGE_USERS
    if normalized.startswith(_AUDIT_PREFIXES):
        return Capability.READ_AUDIT
    if normalized in _ADMIN_NAMES or normalized.startswith(_ADMIN_PREFIXES):
        return Capability.MANAGE_HOSTS
    if read_only or normalized in _READ_COMMANDS:
        return Capability.READ_SCREEN
    return Capability.DRIVE_INPUT


def permitted(name: str, *, read_only: bool = False) -> bool:
    """Whether the active identity can use this server-owned operation."""
    identity = current_authorization()
    return identity is None or can(identity.role, required_capability(name, read_only=read_only))


def require_command(name: str, *, read_only: bool = False) -> None:
    """Guard every nested executor command under a remote request identity."""
    if not permitted(name, read_only=read_only):
        raise AuthorizationError(f'permission denied for {name}')


def resource_permitted(uri: str) -> bool:
    """Apply the same audit/file capabilities to MCP resource discovery and access."""
    if uri.endswith('/history') or uri.endswith('/audit'):
        return permitted('history_read')
    if '://files/' in uri or uri.startswith('file://'):
        return permitted('file_read')
    return permitted('get_mouse_position', read_only=True)


def route_capability(method: str, path: str) -> str:
    """Required capability for a REST route; unknown mutation defaults to admin."""
    if path.startswith('/audit') or path in {'/history', '/metrics'}:
        return Capability.READ_AUDIT
    if path.startswith(('/config', '/usb', '/hosts', '/users')):
        return Capability.MANAGE_USERS if path.startswith('/users') else Capability.MANAGE_HOSTS
    if method == 'GET':
        return Capability.READ_SCREEN
    if path in {'/execute', '/execute_file', '/mouse/click', '/mouse/move',
                '/keyboard/type', '/keyboard/hotkey'}:
        return Capability.DRIVE_INPUT
    return Capability.MANAGE_HOSTS
