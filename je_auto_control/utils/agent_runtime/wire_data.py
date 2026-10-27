"""Resource-free bounded JSON and budget primitives shared by host models and owned transports."""
from __future__ import annotations

import json
import math
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


def detached(value: Any) -> Any:
    """Return bounded JSON data, refusing non-finite numbers and arbitrary objects."""
    try:
        encoded = json.dumps(thaw(value), ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > 1_000_000:
            raise AgentTaskError("task data exceeds one megabyte")
        data = json.loads(encoded)
        pending = [(data, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 32:
                raise AgentTaskError("task data nesting exceeds 32 levels")
            if isinstance(item, dict):
                pending.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                pending.extend((child, depth + 1) for child in item)
        return data
    except (TypeError, ValueError, RecursionError) as error:
        raise AgentTaskError("task data must be finite bounded JSON") from error


def thaw(value: Any) -> Any:
    """Convert immutable contract containers to independent JSON containers."""
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(item) for item in value]
    return value


def positive(value: Any, name: str, maximum: float) -> None:
    """Require a finite positive numeric budget, excluding boolean values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentTaskError(f"{name} must be numeric")
    if not 0 < value <= maximum or not math.isfinite(value):
        raise AgentTaskError(f"{name} must be positive and at most {maximum}")
