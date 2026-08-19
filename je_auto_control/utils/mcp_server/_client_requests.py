"""Server-initiated requests to the MCP client.

MCP is bidirectional: besides answering the client, the server asks *it*
for things — ``roots/list`` to learn the workspace, ``elicitation/create``
to put a question to the user, ``sampling/createMessage`` to borrow the
model. Each one writes a request out and blocks on a slot until the reply
arrives on the inbound side, so the correlation table and the response
router belong together with the senders that populate it.

Destructive-tool confirmation lives here too: it is an elicitation
round-trip, not a tool-execution step.
"""
import json
import threading
from typing import Any, Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server._protocol import (
    _confirm_destructive_enabled, _file_uri_to_path, _MCPError,
)
from je_auto_control.utils.mcp_server.tools import MCPTool


class ClientRequestMixin:
    """Outbound half of the MCP session, mixed into :class:`MCPServer`.

    Requires the host to provide ``_writer``, ``_client_capabilities``,
    ``_resources``, ``_outbound_lock``, ``_pending_outbound``,
    ``_outbound_id_counter`` and ``_sampling_id_counter``.
    """

    @staticmethod
    def _is_outbound_response(method: Optional[str], msg_id: Any,
                             message: Dict[str, Any]) -> bool:
        """True when ``message`` is a reply to a server-initiated request."""
        return (
            method is None
            and msg_id is not None
            and ("result" in message or "error" in message)
        )

    def _dispatch_outbound_response(self, msg_id: Any,
                                    message: Dict[str, Any]) -> None:
        """Route a JSON-RPC response to the matching pending request."""
        with self._outbound_lock:
            slot = self._pending_outbound.get(msg_id)
        if slot is None:
            autocontrol_logger.debug(
                "MCP outbound response for unknown id %r", msg_id,
            )
            return
        if "error" in message:
            slot["error"] = message["error"]
        else:
            slot["result"] = message.get("result")
        slot["event"].set()

    def _maybe_request_roots_async(self) -> None:
        """Fire a roots/list request when the client supports it."""
        if "roots" not in self._client_capabilities:
            return
        if self._writer is None:
            return
        threading.Thread(
            target=self._refresh_roots_safely, daemon=True,
            name="MCPRootsRefresh",
        ).start()

    def _refresh_roots_safely(self) -> None:
        try:
            self.refresh_roots(timeout=5.0)
        except (RuntimeError, TimeoutError) as error:
            autocontrol_logger.info("MCP roots refresh skipped: %r", error)

    def refresh_roots(self, timeout: float = 10.0) -> List[Dict[str, Any]]:
        """Send ``roots/list`` to the client and apply the first root."""
        result = self._send_outbound_request(
            "roots/list", params={}, timeout=timeout,
        )
        roots_list = (result or {}).get("roots") or []
        if not isinstance(roots_list, list) or not roots_list:
            return []
        first_uri = roots_list[0].get("uri") if isinstance(roots_list[0],
                                                            dict) else None
        if isinstance(first_uri, str):
            local_path = _file_uri_to_path(first_uri)
            if local_path:
                self._resources.set_workspace_root(local_path)
                autocontrol_logger.info("MCP workspace root → %s", local_path)
        return roots_list

    def _send_outbound_request(self, method: str,
                               params: Dict[str, Any],
                               timeout: float = 10.0) -> Dict[str, Any]:
        """Send a server-initiated request and wait for the response."""
        writer = self._writer
        if writer is None:
            raise RuntimeError(f"{method} requires an outbound writer")
        request_id = f"srv-{next(self._outbound_id_counter)}"
        slot = {"event": threading.Event()}
        with self._outbound_lock:
            self._pending_outbound[request_id] = slot
        envelope = json.dumps({
            "jsonrpc": "2.0", "id": request_id,
            "method": method, "params": params,
        }, ensure_ascii=False, default=str)
        try:
            writer(envelope)
            if not slot["event"].wait(timeout=timeout):
                raise TimeoutError(f"{method} timed out after {timeout}s")
        finally:
            with self._outbound_lock:
                self._pending_outbound.pop(request_id, None)
        if "error" in slot:
            raise RuntimeError(f"{method} failed: {slot['error']}")
        return slot.get("result") or {}

    def request_elicitation(self, message: str,
                            requested_schema: Optional[Dict[str, Any]] = None,
                            timeout: float = 60.0) -> Dict[str, Any]:
        """Ask the connected client to elicit a response from the user.

        Returns the raw payload (typically ``{"action": "accept" | "decline" | "cancel", ...}``).
        Requires the client to advertise the ``elicitation`` capability.
        """
        params: Dict[str, Any] = {"message": str(message)}
        if requested_schema is not None:
            params["requestedSchema"] = requested_schema
        return self._send_outbound_request(
            "elicitation/create", params=params, timeout=timeout,
        )

    def request_sampling(self, messages: List[Dict[str, Any]],
                         system_prompt: Optional[str] = None,
                         max_tokens: int = 1024,
                         model_preferences: Optional[Dict[str, Any]] = None,
                         timeout: float = 120.0) -> Dict[str, Any]:
        """Ask the connected client to run an LLM sampling request.

        Tools that need the model's help (e.g. an OCR fallback that
        wants the model to identify a UI element from a screenshot)
        can call this and receive the assistant's reply. Requires the
        server to be running in concurrent mode with an outbound
        writer set — typically meaning ``serve_stdio`` or the HTTP
        SSE transport.
        """
        writer = self._writer
        if writer is None:
            raise RuntimeError(
                "request_sampling requires an outbound writer; "
                "start serve_stdio or call set_writer() first",
            )
        request_id = f"sampling-{next(self._sampling_id_counter)}"
        params: Dict[str, Any] = {
            "messages": list(messages),
            "maxTokens": int(max_tokens),
        }
        if system_prompt is not None:
            params["systemPrompt"] = str(system_prompt)
        if model_preferences is not None:
            params["modelPreferences"] = dict(model_preferences)
        slot = {"event": threading.Event()}
        with self._outbound_lock:
            self._pending_outbound[request_id] = slot
        envelope = json.dumps({
            "jsonrpc": "2.0", "id": request_id,
            "method": "sampling/createMessage", "params": params,
        }, ensure_ascii=False, default=str)
        try:
            writer(envelope)
            if not slot["event"].wait(timeout=timeout):
                raise TimeoutError(
                    f"sampling request {request_id} timed out after {timeout}s"
                )
        finally:
            with self._outbound_lock:
                self._pending_outbound.pop(request_id, None)
        if "error" in slot:
            raise RuntimeError(f"sampling failed: {slot['error']}")
        return slot.get("result") or {}

    def _maybe_confirm_destructive(self, name: str, tool: MCPTool,
                                    arguments: Dict[str, Any]) -> None:
        """Ask the client to confirm before running a destructive tool."""
        if not _confirm_destructive_enabled():
            return
        annotations = tool.annotations
        if annotations.read_only or not annotations.destructive:
            return
        if "elicitation" not in self._client_capabilities:
            autocontrol_logger.info(
                "MCP confirmation requested for %s but client lacks "
                "elicitation capability — proceeding without prompt", name,
            )
            return
        if self._writer is None:
            return
        prompt = (f"AutoControl is about to run a destructive tool "
                  f"'{name}'. Continue?")
        try:
            response = self.request_elicitation(
                message=prompt, requested_schema={"type": "object",
                                                    "properties": {}},
                timeout=60.0,
            )
        except (RuntimeError, TimeoutError) as error:
            autocontrol_logger.info(
                "MCP elicitation for %s failed (%r) — refusing call",
                name, error,
            )
            raise _MCPError(
                -32000, f"User confirmation unavailable for {name}",
            ) from error
        action = response.get("action") if isinstance(response, dict) else None
        if action != "accept":
            raise _MCPError(-32000, f"User declined to run {name}: action={action!r}")
        del arguments  # available for future per-arg confirmation policies
