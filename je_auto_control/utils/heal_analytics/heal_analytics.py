"""Analytics over the self-healing event log.

Self-healing without analytics hides accumulating UI drift. This aggregates
the :class:`HealEventLog` into metrics — heal rate, strategy mix, fallback
rate (image template failed, fell back to the VLM), average latency, and the
most-brittle locators — so decaying selectors are surfaced before they fail
outright.

Pure standard library; the log is imported lazily so :func:`heal_stats`
(over supplied events) is unit-testable without any log file.
"""
from typing import Any, Dict, List, Tuple


def _attr(event: Any, name: str) -> Any:
    if isinstance(event, dict):
        return event.get(name)
    return getattr(event, name, None)


def _accumulate(events: List[Any]) -> Tuple[Dict[str, int], Dict[str, int],
                                            List[float], int]:
    by_method: Dict[str, int] = {}
    brittle: Dict[str, int] = {}
    durations: List[float] = []
    fallbacks = 0
    for event in events:
        method = _attr(event, "method") or "?"
        by_method[method] = by_method.get(method, 0) + 1
        if _attr(event, "image_error"):
            fallbacks += 1
            key = (_attr(event, "template_path")
                   or _attr(event, "description") or "?")
            brittle[key] = brittle.get(key, 0) + 1
        duration = _attr(event, "duration_ms")
        if duration is not None:
            durations.append(float(duration))
    return by_method, brittle, durations, fallbacks


def heal_stats(events: List[Any]) -> Dict[str, Any]:
    """Aggregate self-heal events into a metrics dict.

    Each event is a :class:`HealEvent` or dict with ``method`` /
    ``coordinates`` / ``duration_ms`` / ``image_error`` /
    ``template_path`` / ``description``.
    """
    events = list(events)
    total = len(events)
    healed = sum(1 for e in events if _attr(e, "coordinates") is not None)
    by_method, brittle, durations, fallbacks = _accumulate(events)
    top_brittle = sorted(brittle.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return {
        "total": total, "healed": healed,
        "heal_rate": round(healed / total, 4) if total else 0.0,
        "by_method": by_method,
        "fallbacks": fallbacks,
        "fallback_rate": round(fallbacks / total, 4) if total else 0.0,
        "avg_duration_ms": (round(sum(durations) / len(durations), 2)
                            if durations else 0.0),
        "top_brittle": [{"locator": key, "fallbacks": count}
                        for key, count in top_brittle],
    }


def analyze_heal_log(limit: int = 200, log: Any = None) -> Dict[str, Any]:
    """Aggregate the most recent events from the self-heal log."""
    if log is None:
        from je_auto_control.utils.self_healing import default_heal_log
        log = default_heal_log
    return heal_stats(log.list_events(limit=int(limit)))
