"""Viewer authentication and approval for the WebRTC host.

Everything between a viewer's first ``auth`` message and the moment it is
allowed to send input: token check, the auto-approve paths (trust list,
IP whitelist), the manual accept/reject prompt the GUI drives, the SAS
exchange, and the grace-period deadline that closes an unauthenticated
peer. Kept apart from ``webrtc_host`` so the media session lifecycle is
readable on its own.
"""
from __future__ import annotations

import asyncio
from typing import (
    TYPE_CHECKING, Any, Callable, Coroutine, List, Mapping, Optional,
)

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.audit_log import default_audit_log
from je_auto_control.utils.remote_desktop.fingerprint import (
    load_or_create_host_fingerprint,
)
from je_auto_control.utils.remote_desktop.webrtc_transport import get_bridge

if TYPE_CHECKING:  # imported lazily at runtime to keep startup cheap
    from je_auto_control.utils.remote_desktop.permissions import (
        SessionPermissions,
    )
    from je_auto_control.utils.remote_desktop.trust_list import TrustList


class ViewerAuthMixin:
    """Auth half of :class:`WebRTCDesktopHost`.

    Requires the host to provide ``_token``, ``_trust_list``,
    ``_ip_whitelist``, ``_authenticated``, ``_pending_viewer_id``,
    ``_send_ctrl``, ``_spawn_bg`` and ``_async_stop``.
    """

    if TYPE_CHECKING:
        # Declared, never defined: the host class this is mixed into owns
        # every one of these. The block is stripped at runtime, so nothing
        # here can shadow what the host actually binds.
        _token: str
        _trust_list: Optional["TrustList"]
        _ip_whitelist: List[str]
        _permissions: "SessionPermissions"
        _remote_ip: Optional[str]
        _authenticated: bool
        _auth_deadline_handle: Optional[asyncio.TimerHandle]
        _on_authenticated: Optional[Callable[[], None]]
        _on_pending_viewer: Optional[Callable[[], None]]
        _send_ctrl: Callable[[Mapping[str, Any]], None]
        _spawn_bg: Callable[[Any], asyncio.Task]
        _async_stop: Callable[[], Coroutine[Any, Any, None]]

    def _handle_send_sas(self) -> None:
        try:
            from je_auto_control.utils.remote_desktop.session_actions import (
                send_secure_attention_sequence,
            )
            send_secure_attention_sequence()
            self._send_ctrl({"type": "sas_ok"})
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("SendSAS: %r", error)
            self._send_ctrl({"type": "sas_fail", "error": str(error)})

    def _handle_auth(self, data: Mapping[str, Any]) -> None:
        token = data.get("token")
        if not isinstance(token, str) or token != self._token:
            self._reject_auth(data)
            return
        viewer_id = data.get("viewer_id")
        self._pending_viewer_id = (
            viewer_id if isinstance(viewer_id, str) else None
        )
        if self._auto_approve_via_trust():
            return
        if self._auto_approve_via_whitelist():
            return
        if self._on_pending_viewer is None:
            self._approve_pending_viewer()
            return
        self._has_pending_viewer = True
        try:
            self._on_pending_viewer()
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("pending viewer cb: %r", error)

    def _reject_auth(self, data: Mapping[str, Any]) -> None:
        self._send_ctrl({"type": "auth_fail"})
        try:
            default_audit_log().log(
                "auth_fail",
                viewer_id=str(data.get("viewer_id", "")) or None,
                detail=f"remote_ip={self._remote_ip}",
            )
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("audit log auth_fail: %r", error)
        get_bridge().call_soon(self._schedule_close_after_fail)

    def _auto_approve_via_trust(self) -> bool:
        # The emptiness check is what `_is_trusted_viewer` does first anyway;
        # hoisting it makes the non-empty id available to `touch` below.
        viewer_id = self._pending_viewer_id
        if not viewer_id or not self._is_trusted_viewer(viewer_id):
            return False
        autocontrol_logger.info(
            "webrtc host: viewer_id %s is trusted; auto-approving", viewer_id,
        )
        if self._trust_list is not None:
            try:
                self._trust_list.touch(viewer_id)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("trust touch: %r", error)
        self._approve_pending_viewer()
        return True

    def _auto_approve_via_whitelist(self) -> bool:
        if not self._is_ip_whitelisted(self._remote_ip):
            return False
        autocontrol_logger.info(
            "webrtc host: remote ip %s matches whitelist; auto-approving",
            self._remote_ip,
        )
        self._approve_pending_viewer()
        return True

    def _is_ip_whitelisted(self, ip: Optional[str]) -> bool:
        if not ip or not self._ip_whitelist:
            return False
        import ipaddress
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        for cidr in self._ip_whitelist:
            try:
                if addr in ipaddress.ip_network(cidr.strip(), strict=False):
                    return True
            except ValueError:
                continue
        return False

    def _is_trusted_viewer(self, viewer_id: Optional[str]) -> bool:
        if self._trust_list is None or not viewer_id:
            return False
        try:
            return self._trust_list.is_trusted(viewer_id)
        except (OSError, RuntimeError) as error:
            autocontrol_logger.warning("trust list check: %r", error)
            return False

    def trust_pending_viewer(self, label: str = "") -> None:
        """Add the current pending viewer to the trust list, then approve."""
        viewer_id = self._pending_viewer_id
        if self._trust_list is not None and viewer_id:
            try:
                self._trust_list.add(viewer_id, label=label)
            except (OSError, ValueError, RuntimeError) as error:
                autocontrol_logger.warning("trust list add: %r", error)
        self.approve_pending_viewer()

    @property
    def pending_viewer_id(self) -> Optional[str]:
        return self._pending_viewer_id

    def approve_pending_viewer(self) -> None:
        """Thread-safe accept; call from GUI when user clicks Accept."""
        get_bridge().call_soon(self._approve_pending_viewer)

    def reject_pending_viewer(self) -> None:
        """Thread-safe reject; call from GUI when user clicks Reject."""
        get_bridge().call_soon(self._reject_pending_viewer)

    def _approve_pending_viewer(self) -> None:
        if not self._has_pending_viewer and self._authenticated:
            return
        self._has_pending_viewer = False
        self._authenticated = True
        self._send_ctrl({
            "type": "auth_ok",
            "read_only": not self._permissions.allow_input,
            "permissions": self._permissions.to_dict(),
            "fingerprint": load_or_create_host_fingerprint(),
        })
        try:
            default_audit_log().log(
                "auth_ok",
                viewer_id=self._pending_viewer_id,
                detail=f"remote_ip={self._remote_ip}",
            )
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("audit log auth_ok: %r", error)
        if self._auth_deadline_handle is not None:
            self._auth_deadline_handle.cancel()
            self._auth_deadline_handle = None
        if self._on_authenticated is not None:
            try:
                self._on_authenticated()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.warning("auth cb: %r", error)

    def _reject_pending_viewer(self) -> None:
        self._has_pending_viewer = False
        self._send_ctrl({"type": "auth_fail"})
        get_bridge().call_soon(self._schedule_close_after_fail)

    @property
    def has_pending_viewer(self) -> bool:
        return self._has_pending_viewer

    def _schedule_close_after_fail(self) -> None:
        loop = asyncio.get_event_loop()
        loop.call_later(0.5, lambda: self._spawn_bg(self._async_stop()))

    def _enforce_auth_deadline(self) -> None:
        if self._authenticated:
            return
        autocontrol_logger.warning(
            "webrtc host: viewer failed to authenticate within grace period",
        )
        self._spawn_bg(self._async_stop())
