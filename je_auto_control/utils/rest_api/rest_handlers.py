"""Endpoint implementations for the REST API.

Each function takes a ``RouteContext`` (decoded query / body / authn flag)
and returns ``(status_code, payload_dict)``. Keeping the handlers pure
makes them trivial to unit-test without an HTTP layer; the dispatcher in
``rest_server`` just routes path → handler and writes the JSON.
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


@dataclass
class RouteContext:
    """Per-request input handed to handler functions."""

    query: str
    body: Optional[Any]
    client_ip: str

    def query_params(self) -> Dict[str, List[str]]:
        return parse_qs(self.query) if self.query else {}

    def query_first(self, key: str, default: Optional[str] = None) -> Optional[str]:
        values = self.query_params().get(key)
        return values[0] if values else default


HandlerResult = Tuple[int, Dict[str, Any]]


def handle_health(_ctx: RouteContext) -> HandlerResult:
    return 200, {"status": "ok"}


def handle_jobs(_ctx: RouteContext) -> HandlerResult:
    from je_auto_control.utils.scheduler.scheduler import default_scheduler
    jobs = [
        {"job_id": j.job_id, "script_path": j.script_path,
         "interval_seconds": j.interval_seconds, "is_cron": j.is_cron,
         "repeat": j.repeat, "runs": j.runs, "enabled": j.enabled}
        for j in default_scheduler.list_jobs()
    ]
    return 200, {"jobs": jobs}


def handle_history(ctx: RouteContext) -> HandlerResult:
    from je_auto_control.utils.run_history.history_store import default_history_store
    try:
        limit = int(ctx.query_first("limit", "100") or "100")
    except ValueError:
        limit = 100
    source_type = ctx.query_first("source_type") or None
    try:
        rows = default_history_store.list_runs(
            limit=limit, source_type=source_type,
        )
    except ValueError:
        return 200, {"runs": []}
    return 200, {"runs": [_serialize_history_row(r) for r in rows]}


def handle_screenshot(_ctx: RouteContext) -> HandlerResult:
    """Return a base64 PNG so it travels in JSON cleanly."""
    try:
        from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
        image = pil_screenshot()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    except (OSError, RuntimeError, ValueError, ImportError) as error:
        autocontrol_logger.error("rest screenshot failed: %r", error)
        return 500, {"error": "screenshot failed"}
    return 200, {"format": "png", "encoding": "base64", "data": encoded}


def handle_mouse_position(_ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.wrapper.auto_control_mouse import get_mouse_position
        pos = get_mouse_position()
    except (OSError, RuntimeError, ImportError) as error:
        autocontrol_logger.error("rest mouse_position failed: %r", error)
        return 500, {"error": "mouse_position failed"}
    if pos is None:
        return 500, {"error": "mouse_position unavailable"}
    return 200, {"x": int(pos[0]), "y": int(pos[1])}


def handle_screen_size(_ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.wrapper.auto_control_screen import screen_size
        width, height = screen_size()
    except (OSError, RuntimeError, ImportError) as error:
        autocontrol_logger.error("rest screen_size failed: %r", error)
        return 500, {"error": "screen_size failed"}
    return 200, {"width": int(width), "height": int(height)}


def handle_windows(_ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.wrapper.auto_control_window import list_windows
        wins = list_windows()
    except NotImplementedError:
        return 200, {"windows": [], "platform_supported": False}
    except (OSError, RuntimeError, ImportError) as error:
        autocontrol_logger.error("rest windows failed: %r", error)
        return 500, {"error": "windows failed"}
    return 200, {
        "windows": [{"hwnd": int(h), "title": str(t)} for h, t in wins],
    }


def handle_remote_sessions(_ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.utils.remote_desktop.registry import registry
        return 200, {
            "host": registry.host_status(),
            "viewer": registry.viewer_status(),
        }
    except (RuntimeError, AttributeError, ImportError) as error:
        autocontrol_logger.error("rest sessions failed: %r", error)
        return 500, {"error": "sessions failed"}


def handle_commands(_ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.utils.executor.action_executor import executor
        names = sorted(executor.event_dict.keys())
    except (RuntimeError, AttributeError) as error:
        autocontrol_logger.error("rest commands failed: %r", error)
        return 500, {"error": "commands failed"}
    return 200, {"commands": names, "count": len(names)}


def handle_execute(ctx: RouteContext) -> HandlerResult:
    if not isinstance(ctx.body, dict):
        return 400, {"error": "body must be JSON object"}
    actions = ctx.body.get("actions")
    if actions is None:
        return 400, {"error": "missing 'actions' field"}
    try:
        from je_auto_control.utils.executor.action_executor import execute_action
        result = execute_action(actions)
    except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: REST boundary must always return JSON, never drop the HTTP response
        autocontrol_logger.error("rest execute failed: %r", error)
        return 500, {"error": "execute_action failed"}
    return 200, {"result": result}


def handle_execute_file(ctx: RouteContext) -> HandlerResult:
    if not isinstance(ctx.body, dict):
        return 400, {"error": "body must be JSON object"}
    path = ctx.body.get("path")
    if not isinstance(path, str) or not path:
        return 400, {"error": "missing 'path' field"}
    try:
        from je_auto_control.utils.executor.action_executor import execute_files
        result = execute_files([path])
    except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: REST boundary must always return JSON, never drop the HTTP response
        autocontrol_logger.error("rest execute_file failed: %r", error)
        return 500, {"error": "execute_files failed"}
    return 200, {"result": result}


def _serialize_history_row(row: Any) -> Dict[str, Any]:
    return {
        "id": row.id, "source_type": row.source_type,
        "source_id": row.source_id, "script_path": row.script_path,
        "started_at": str(row.started_at),
        "finished_at": str(row.finished_at) if row.finished_at else None,
        "status": row.status, "error_text": row.error_text,
        "duration_seconds": row.duration_seconds,
    }


def handle_audit_list(ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.utils.remote_desktop.audit_log import (
            default_audit_log,
        )
        try:
            limit = int(ctx.query_first("limit", "200") or "200")
        except ValueError:
            limit = 200
        rows = default_audit_log().query(
            event_type=ctx.query_first("event_type"),
            host_id=ctx.query_first("host_id"),
            limit=limit,
        )
    except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: REST boundary must always return JSON
        autocontrol_logger.error("rest audit_list failed: %r", error)
        return 500, {"error": "audit_list failed"}
    return 200, {"rows": rows, "count": len(rows)}


def handle_inspector_recent(ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.utils.remote_desktop.webrtc_inspector import (
            default_webrtc_inspector,
        )
        try:
            n = int(ctx.query_first("n", "60") or "60")
        except ValueError:
            n = 60
        rows = default_webrtc_inspector().recent(n)
    except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: REST boundary must always return JSON
        autocontrol_logger.error("rest inspector_recent failed: %r", error)
        return 500, {"error": "inspector_recent failed"}
    return 200, {"samples": rows, "count": len(rows)}


def handle_config_export(_ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.utils.config_bundle import export_config_bundle
        bundle = export_config_bundle()
    except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: REST boundary must always return JSON
        autocontrol_logger.error("rest config_export failed: %r", error)
        return 500, {"error": "config_export failed"}
    return 200, bundle


def handle_config_import(ctx: RouteContext) -> HandlerResult:
    if not isinstance(ctx.body, dict):
        return 400, {"error": "body must be a JSON bundle object"}
    try:
        from je_auto_control.utils.config_bundle import (
            ConfigBundleError, import_config_bundle,
        )
        report = import_config_bundle(ctx.body, dry_run=False)
    except ConfigBundleError as error:
        return 400, {"error": f"bundle rejected: {error}"}
    except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: REST boundary must always return JSON
        autocontrol_logger.error("rest config_import failed: %r", error)
        return 500, {"error": "config_import failed"}
    return 200, report.to_dict()


def handle_openapi(_ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.utils.rest_api.rest_openapi import (
            build_openapi_spec,
        )
        spec = build_openapi_spec()
    except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: REST boundary must always return JSON
        autocontrol_logger.error("rest openapi failed: %r", error)
        return 500, {"error": "openapi failed"}
    return 200, spec


def handle_diagnose(_ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.utils.diagnostics.diagnostics import run_diagnostics
        report = run_diagnostics()
    except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: REST boundary must always return JSON
        autocontrol_logger.error("rest diagnose failed: %r", error)
        return 500, {"error": "diagnose failed"}
    return 200, report.to_dict()


def handle_usb_devices(_ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.utils.usb.usb_devices import list_usb_devices
        result = list_usb_devices()
    except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: REST boundary must always return JSON
        autocontrol_logger.error("rest usb_devices failed: %r", error)
        return 500, {"error": "usb_devices failed"}
    return 200, result.to_dict()


def handle_usb_events(ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.utils.usb.usb_watcher import default_usb_watcher
        try:
            since = int(ctx.query_first("since", "0") or "0")
        except ValueError:
            since = 0
        try:
            limit_text = ctx.query_first("limit")
            limit = int(limit_text) if limit_text else None
        except ValueError:
            limit = None
        events = default_usb_watcher().recent_events(since=since, limit=limit)
    except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: REST boundary must always return JSON
        autocontrol_logger.error("rest usb_events failed: %r", error)
        return 500, {"error": "usb_events failed"}
    return 200, {
        "events": events,
        "count": len(events),
        "watcher_running": default_usb_watcher().is_running,
    }


def handle_inspector_summary(_ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.utils.remote_desktop.webrtc_inspector import (
            default_webrtc_inspector,
        )
        return 200, default_webrtc_inspector().summary()
    except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: REST boundary must always return JSON
        autocontrol_logger.error("rest inspector_summary failed: %r", error)
        return 500, {"error": "inspector_summary failed"}


def handle_audit_verify(_ctx: RouteContext) -> HandlerResult:
    try:
        from je_auto_control.utils.remote_desktop.audit_log import (
            default_audit_log,
        )
        result = default_audit_log().verify_chain()
    except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: REST boundary must always return JSON
        autocontrol_logger.error("rest audit_verify failed: %r", error)
        return 500, {"error": "audit_verify failed"}
    return 200, {
        "ok": result.ok,
        "broken_at_id": result.broken_at_id,
        "total_rows": result.total_rows,
    }


__all__ = [
    "RouteContext", "HandlerResult",
    "handle_health", "handle_jobs", "handle_history",
    "handle_screenshot", "handle_mouse_position", "handle_screen_size",
    "handle_windows", "handle_remote_sessions", "handle_commands",
    "handle_execute", "handle_execute_file",
    "handle_audit_list", "handle_audit_verify",
    "handle_inspector_recent", "handle_inspector_summary",
    "handle_usb_devices", "handle_usb_events", "handle_diagnose",
    "handle_openapi", "handle_config_export", "handle_config_import",
]
