"""Build the OpenAPI 3.1 spec for the REST API by walking its route table.

The route metadata (summary, parameters, sample response) lives in a
single ``_ENDPOINT_METADATA`` mapping below — keeping it adjacent to the
generator means it's easy to spot when a new route lands without doc
coverage. The companion drift test in
``test_rest_openapi.test_every_route_has_metadata`` enforces that.

Only routes that actually exist at runtime end up in the spec. We do
*not* invent endpoints — the goal is "what is reachable", not "what
might be nice".
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


_BEARER_SCHEME_NAME = "BearerAuth"
_API_VERSION = "1.0.0"
_JSON_MEDIA_TYPE = "application/json"


# Per-endpoint metadata. Each value is a dict with keys:
#   - summary: one-line human description
#   - tag:     grouping for Swagger UI
#   - params:  list of OpenAPI Parameter Objects (query strings only here)
#   - request_body: optional schema dict for POST bodies
#   - public:  True if the endpoint is intentionally unauthenticated
_ENDPOINT_METADATA: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("GET", "/health"): {
        "summary": "Liveness probe (unauthenticated).",
        "tag": "system", "public": True,
    },
    ("GET", "/screen_size"): {
        "summary": "Current screen resolution.",
        "tag": "system",
    },
    ("GET", "/mouse_position"): {
        "summary": "Current mouse coordinates.",
        "tag": "system",
    },
    ("GET", "/sessions"): {
        "summary": "Remote desktop host + viewer status.",
        "tag": "remote-desktop",
    },
    ("GET", "/commands"): {
        "summary": "List of registered AC_* executor commands.",
        "tag": "executor",
    },
    ("GET", "/jobs"): {
        "summary": "Scheduler job list.",
        "tag": "scheduler",
    },
    ("GET", "/history"): {
        "summary": "Recent run history.",
        "tag": "history",
        "params": [
            {"name": "limit", "in": "query", "required": False,
             "schema": {"type": "integer", "default": 100}},
            {"name": "source_type", "in": "query", "required": False,
             "schema": {"type": "string"}},
        ],
    },
    ("GET", "/screenshot"): {
        "summary": "Base64 PNG screenshot of the current screen.",
        "tag": "system",
    },
    ("GET", "/windows"): {
        "summary": "List of OS windows (Windows-only today).",
        "tag": "system",
    },
    ("GET", "/audit/list"): {
        "summary": "Recent audit log rows.",
        "tag": "audit",
        "params": [
            {"name": "event_type", "in": "query", "required": False,
             "schema": {"type": "string"}},
            {"name": "host_id", "in": "query", "required": False,
             "schema": {"type": "string"}},
            {"name": "limit", "in": "query", "required": False,
             "schema": {"type": "integer", "default": 200}},
        ],
    },
    ("GET", "/audit/verify"): {
        "summary": "Walk the audit hash chain; report ok / broken_at_id.",
        "tag": "audit",
    },
    ("GET", "/inspector/recent"): {
        "summary": "Most recent N WebRTC stats samples.",
        "tag": "inspector",
        "params": [
            {"name": "n", "in": "query", "required": False,
             "schema": {"type": "integer", "default": 60}},
        ],
    },
    ("GET", "/inspector/summary"): {
        "summary": "Per-metric last/min/max/avg/p95 over the rolling window.",
        "tag": "inspector",
    },
    ("GET", "/usb/devices"): {
        "summary": "Enumerate connected USB devices (read-only).",
        "tag": "usb",
    },
    ("GET", "/usb/events"): {
        "summary": "Recent USB hotplug events (since=<seq>).",
        "tag": "usb",
        "params": [
            {"name": "since", "in": "query", "required": False,
             "schema": {"type": "integer", "default": 0}},
            {"name": "limit", "in": "query", "required": False,
             "schema": {"type": "integer"}},
        ],
    },
    ("GET", "/diagnose"): {
        "summary": "Run subsystem diagnostics; return per-check results.",
        "tag": "system",
    },
    ("POST", "/execute"): {
        "summary": "Run an action list through the executor.",
        "tag": "executor",
        "request_body": {
            "type": "object",
            "required": ["actions"],
            "properties": {
                "actions": {
                    "type": "array",
                    "description": "List of [command, args] action tuples.",
                    "items": {"type": "array"},
                },
            },
        },
    },
    ("POST", "/execute_file"): {
        "summary": "Run a JSON action file by absolute path.",
        "tag": "executor",
        "request_body": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string"},
            },
        },
    },
    ("POST", "/config/export"): {
        "summary": "Export AutoControl user config as a JSON bundle.",
        "tag": "config",
        "request_body": {
            "type": "object",
            "description": "Empty body; the bundle is returned in the response.",
        },
    },
    ("POST", "/config/import"): {
        "summary": "Apply a previously-exported config bundle.",
        "tag": "config",
        "request_body": {
            "type": "object",
            "required": ["manifest", "files"],
            "properties": {
                "manifest": {"type": "object"},
                "files": {"type": "object"},
            },
        },
    },
    # The non-JSON endpoints surfaced for completeness.
    ("GET", "/metrics"): {
        "summary": "Prometheus exposition (text/plain).",
        "tag": "system",
        "non_json_response": "text/plain",
    },
    ("GET", "/dashboard"): {
        "summary": "Web admin dashboard HTML shell (unauthenticated).",
        "tag": "system",
        "public": True,
        "non_json_response": "text/html",
    },
    ("GET", "/openapi.json"): {
        "summary": "This OpenAPI 3.1 spec.",
        "tag": "system",
    },
    ("GET", "/docs"): {
        "summary": "Swagger UI HTML shell (unauthenticated).",
        "tag": "system",
        "public": True,
        "non_json_response": "text/html",
    },
}


def known_endpoints() -> List[Tuple[str, str]]:
    """Return ``(method, path)`` tuples for every documented endpoint."""
    return list(_ENDPOINT_METADATA.keys())


def build_openapi_spec(*, server_url: str = "http://127.0.0.1:9939",
                       title: str = "AutoControl REST API",
                       version: str = _API_VERSION) -> Dict[str, Any]:
    """Build the OpenAPI 3.1 spec dict from ``_ENDPOINT_METADATA``.

    No I/O, no global state — pure function so the result can be cached
    by the caller and so tests can assert on its exact shape.
    """
    paths: Dict[str, Dict[str, Any]] = {}
    for (method, path), meta in _ENDPOINT_METADATA.items():
        path_item = paths.setdefault(path, {})
        path_item[method.lower()] = _operation_object(method, path, meta)

    return {
        "openapi": "3.1.0",
        "info": {
            "title": title,
            "version": version,
            "description": (
                "AutoControl REST API. All non-public endpoints require "
                "an `Authorization: Bearer <token>` header. The bearer "
                "token is generated at server start and surfaced via the "
                "REST API GUI tab or the CLI."
            ),
        },
        "servers": [{"url": server_url}],
        "components": {
            "securitySchemes": {
                _BEARER_SCHEME_NAME: {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Bearer token issued by the REST server.",
                },
            },
        },
        "security": [{_BEARER_SCHEME_NAME: []}],
        "tags": _build_tags(),
        "paths": paths,
    }


def _operation_object(method: str, path: str,
                      meta: Dict[str, Any]) -> Dict[str, Any]:
    op: Dict[str, Any] = {
        "summary": meta.get("summary", ""),
        "tags": [meta.get("tag", "system")],
        "responses": _build_responses(meta),
        "operationId": _operation_id(method, path),
    }
    if meta.get("public"):
        op["security"] = []  # explicit empty array overrides global security
    if meta.get("params"):
        op["parameters"] = list(meta["params"])
    if meta.get("request_body"):
        op["requestBody"] = {
            "required": True,
            "content": {
                _JSON_MEDIA_TYPE: {"schema": meta["request_body"]},
            },
        }
    return op


def _build_responses(meta: Dict[str, Any]) -> Dict[str, Any]:
    media_type = meta.get("non_json_response", _JSON_MEDIA_TYPE)
    schema = ({"type": "string"} if media_type != _JSON_MEDIA_TYPE
              else {"type": "object"})
    responses: Dict[str, Any] = {
        "200": {
            "description": "Success.",
            "content": {media_type: {"schema": schema}},
        },
    }
    if not meta.get("public"):
        responses["401"] = {
            "description": "Missing or wrong bearer token.",
            "content": {_JSON_MEDIA_TYPE: {"schema": _error_schema()}},
        }
        responses["429"] = {
            "description": "Rate limited or locked out after repeated auth failures.",
            "content": {_JSON_MEDIA_TYPE: {"schema": _error_schema()}},
        }
    if meta.get("request_body"):
        responses["400"] = {
            "description": "Bad request body.",
            "content": {_JSON_MEDIA_TYPE: {"schema": _error_schema()}},
        }
    return responses


def _error_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "error": {"type": "string"},
        },
    }


def _operation_id(method: str, path: str) -> str:
    cleaned = path.strip("/").replace("/", "_") or "root"
    return f"{method.lower()}_{cleaned}"


def _build_tags() -> List[Dict[str, str]]:
    descriptions = {
        "system": "Process / OS / dashboard endpoints.",
        "executor": "Run actions and inspect the executor command set.",
        "scheduler": "Background scheduled jobs.",
        "history": "Persistent run history.",
        "remote-desktop": "Remote desktop host + viewer registry.",
        "audit": "Tamper-evident audit log.",
        "inspector": "Live WebRTC stats inspector.",
        "usb": "USB device enumeration + hotplug events.",
        "config": "Export / import the user configuration bundle.",
    }
    return [{"name": name, "description": desc}
            for name, desc in sorted(descriptions.items())]


__all__ = [
    "build_openapi_spec", "known_endpoints",
]
