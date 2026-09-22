"""MCP adapters for the scheduler, triggers and the hotkey daemon.

Same contract as :mod:`._handlers` -- normalise arguments and return values so
they survive the JSON-RPC boundary, with every project import lazy -- split out
by theme because ``_handlers.py`` is over the 750-line limit.
"""
import os
from typing import Any, Dict, List, Optional


# === Scheduler / triggers / hotkey daemon ===================================

def _job_to_dict(job: Any) -> Dict[str, Any]:
    return {
        "job_id": job.job_id, "script_path": job.script_path,
        "interval_seconds": job.interval_seconds,
        "is_cron": job.is_cron, "repeat": job.repeat,
        "max_runs": job.max_runs, "runs": job.runs,
        "enabled": job.enabled,
    }


def scheduler_add_job(script_path: str,
                      interval_seconds: Optional[float] = None,
                      cron_expression: Optional[str] = None,
                      repeat: bool = True,
                      max_runs: Optional[int] = None,
                      job_id: Optional[str] = None) -> Dict[str, Any]:
    """Add an interval or cron job to the default scheduler."""
    from je_auto_control.utils.scheduler.scheduler import default_scheduler
    safe_path = os.path.realpath(os.fspath(script_path))
    if cron_expression:
        job = default_scheduler.add_cron_job(
            safe_path, cron_expression, max_runs=max_runs, job_id=job_id,
        )
        return _job_to_dict(job)
    if interval_seconds is None:
        raise ValueError("scheduler_add_job needs either interval_seconds or cron_expression")
    job = default_scheduler.add_job(
        safe_path, interval_seconds=float(interval_seconds),
        repeat=bool(repeat), max_runs=max_runs, job_id=job_id,
    )
    return _job_to_dict(job)


def scheduler_remove_job(job_id: str) -> bool:
    from je_auto_control.utils.scheduler.scheduler import default_scheduler
    return bool(default_scheduler.remove_job(job_id))


def scheduler_list_jobs() -> List[Dict[str, Any]]:
    from je_auto_control.utils.scheduler.scheduler import default_scheduler
    return [_job_to_dict(job) for job in default_scheduler.list_jobs()]


def scheduler_start() -> str:
    from je_auto_control.utils.scheduler.scheduler import default_scheduler
    default_scheduler.start()
    return "started"


def scheduler_stop() -> str:
    from je_auto_control.utils.scheduler.scheduler import default_scheduler
    default_scheduler.stop()
    return "stopped"


def _trigger_to_dict(trigger: Any) -> Dict[str, Any]:
    return {
        "trigger_id": trigger.trigger_id,
        "type": type(trigger).__name__,
        "script_path": trigger.script_path,
        "repeat": trigger.repeat, "enabled": trigger.enabled,
        "fired": trigger.fired,
    }


def trigger_add(kind: str, script_path: str, repeat: bool = False,
                image_path: Optional[str] = None,
                threshold: float = 0.8,
                title_substring: Optional[str] = None,
                case_sensitive: bool = False,
                x: int = 0, y: int = 0,
                target_rgb: Optional[List[int]] = None,
                tolerance: int = 8,
                watch_path: Optional[str] = None) -> Dict[str, Any]:
    """Add a trigger to the default engine. ``kind`` is image/window/pixel/file."""
    from je_auto_control.utils.triggers.trigger_engine import (
        FilePathTrigger, ImageAppearsTrigger, PixelColorTrigger,
        WindowAppearsTrigger, default_trigger_engine,
    )
    safe_script = os.path.realpath(os.fspath(script_path))
    trigger = _build_trigger(
        kind=kind, script_path=safe_script, repeat=repeat,
        image_path=image_path, threshold=threshold,
        title_substring=title_substring, case_sensitive=case_sensitive,
        x=x, y=y, target_rgb=target_rgb, tolerance=tolerance,
        watch_path=watch_path,
        types={
            "image": ImageAppearsTrigger,
            "window": WindowAppearsTrigger,
            "pixel": PixelColorTrigger,
            "file": FilePathTrigger,
        },
    )
    default_trigger_engine.add(trigger)
    return _trigger_to_dict(trigger)


def _build_trigger(*, kind: str, script_path: str, repeat: bool,
                   image_path: Optional[str], threshold: float,
                   title_substring: Optional[str], case_sensitive: bool,
                   x: int, y: int, target_rgb: Optional[List[int]],
                   tolerance: int, watch_path: Optional[str],
                   types: Dict[str, Any]) -> Any:
    if kind == "image":
        if not image_path:
            raise ValueError("image trigger requires image_path")
        return types["image"](trigger_id="", script_path=script_path,
                               repeat=repeat, image_path=image_path,
                               threshold=float(threshold))
    if kind == "window":
        if not title_substring:
            raise ValueError("window trigger requires title_substring")
        return types["window"](trigger_id="", script_path=script_path,
                                repeat=repeat,
                                title_substring=title_substring,
                                case_sensitive=bool(case_sensitive))
    if kind == "pixel":
        rgb = tuple(int(c) for c in (target_rgb or [0, 0, 0]))
        return types["pixel"](trigger_id="", script_path=script_path,
                               repeat=repeat, x=int(x), y=int(y),
                               target_rgb=rgb, tolerance=int(tolerance))
    if kind == "file":
        if not watch_path:
            raise ValueError("file trigger requires watch_path")
        return types["file"](trigger_id="", script_path=script_path,
                              repeat=repeat, watch_path=watch_path)
    raise ValueError(f"unknown trigger kind: {kind!r}")


def trigger_remove(trigger_id: str) -> bool:
    from je_auto_control.utils.triggers.trigger_engine import default_trigger_engine
    return bool(default_trigger_engine.remove(trigger_id))


def trigger_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.triggers.trigger_engine import default_trigger_engine
    return [_trigger_to_dict(t) for t in default_trigger_engine.list_triggers()]


def trigger_start() -> str:
    from je_auto_control.utils.triggers.trigger_engine import default_trigger_engine
    default_trigger_engine.start()
    return "started"


def trigger_stop() -> str:
    from je_auto_control.utils.triggers.trigger_engine import default_trigger_engine
    default_trigger_engine.stop()
    return "stopped"


def hotkey_bind(combo: str, script_path: str,
                binding_id: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon
    safe_path = os.path.realpath(os.fspath(script_path))
    binding = default_hotkey_daemon.bind(combo, safe_path,
                                          binding_id=binding_id)
    return {
        "binding_id": binding.binding_id, "combo": binding.combo,
        "script_path": binding.script_path, "enabled": binding.enabled,
        "fired": binding.fired,
    }


def hotkey_unbind(binding_id: str) -> bool:
    from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon
    return bool(default_hotkey_daemon.unbind(binding_id))


def hotkey_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon
    return [{
        "binding_id": b.binding_id, "combo": b.combo,
        "script_path": b.script_path, "enabled": b.enabled,
        "fired": b.fired,
    } for b in default_hotkey_daemon.list_bindings()]


def hotkey_daemon_start() -> str:
    from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon
    default_hotkey_daemon.start()
    return "started"


def hotkey_daemon_stop() -> str:
    from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon
    default_hotkey_daemon.stop()
    return "stopped"
