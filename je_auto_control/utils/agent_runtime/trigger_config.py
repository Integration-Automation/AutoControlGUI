"""Validate durable trigger schedules and rooted file-version notifications without side effects."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import positive
from je_auto_control.utils.agent_runtime.policy import TaskPolicy

KINDS = ("interval", "cron", "file", "event")


def validate_config(kind: str, config: dict, policy: TaskPolicy) -> dict[str, Any]:
    """Require explicit schedule fields; event input can never select a task scope."""
    fields = {"interval": {"seconds"}, "cron": {"expression", "timezone"},
              "file": {"path", "stable_seconds"}, "event": set()}
    if not isinstance(kind, str) or kind not in fields or not isinstance(config, dict) or set(config) - fields[kind]:
        raise AgentTaskError("unknown trigger kind or configuration fields")
    checks = {"interval": _interval, "cron": _cron, "file": lambda value: _file(value, policy),
              "event": lambda _value: {}}
    return checks[kind](config)


def _interval(config: dict) -> dict:
    positive(config.get("seconds"), "trigger seconds", 86400 * 365)
    seconds = float(config["seconds"])
    if seconds < 1:
        raise AgentTaskError("trigger intervals must be at least one second")
    return {"seconds": seconds}


def _cron(config: dict) -> dict:
    from je_auto_control.utils.scheduler.cron import parse_cron
    expression, timezone = config.get("expression"), config.get("timezone", "UTC")
    if not isinstance(expression, str) or len(expression) > 128 or not isinstance(timezone, str):
        raise AgentTaskError("cron requires a bounded expression and timezone")
    try:
        parse_cron(expression)
        _timezone(timezone)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise AgentTaskError("cron expression or timezone is unavailable") from error
    return {"expression": expression, "timezone": timezone}


def _file(config: dict, policy: TaskPolicy) -> dict:
    path = policy.path(config.get("path"))
    stable = config.get("stable_seconds", 1)
    positive(stable, "file stability seconds", 300)
    if Path(path).exists() and not Path(path).is_file():
        raise AgentTaskError("file triggers require a file path")
    return {"path": path, "stable_seconds": stable}


def next_due(kind: str, config: dict, now: float) -> float:
    """Reuse the existing cron parser; missed schedule windows coalesce rather than replay a backlog."""
    if kind == "interval":
        return now + config["seconds"]
    if kind == "cron":
        from je_auto_control.utils.scheduler.cron import next_match, parse_cron
        current = dt.datetime.fromtimestamp(now, _timezone(config["timezone"]))
        return next_match(parse_cron(config["expression"]), current).timestamp()
    return 0.0


def _timezone(name: str) -> dt.tzinfo:
    return dt.timezone.utc if name == "UTC" else ZoneInfo(name)
