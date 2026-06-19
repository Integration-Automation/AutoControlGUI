"""Reactive screen observer — fire a callback when something changes.

The blocking ``wait_for_*`` helpers cover "pause until X appears". This is
the complementary *non-blocking* model (SikuliX's ``observe``): register
watches on a region/predicate and get a callback when the watched thing
**appears**, **vanishes**, or **changes** — so a flow can react to dialogs,
progress, or status changes while doing other work.

A :class:`WatchRule` pairs a ``predicate`` (returns the current value /
presence) with an ``on_event`` callback. Detection is decoupled from the
screen: predicates are injectable, so transition logic is unit-tested with
synthetic values via :meth:`ScreenObserver.poll_once`; :meth:`start` adds an
optional background polling thread. Imports no ``PySide6`` — fully headless.
"""
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

EVENT_APPEAR = "appear"
EVENT_VANISH = "vanish"
EVENT_CHANGE = "change"
_ALL_EVENTS = (EVENT_APPEAR, EVENT_VANISH, EVENT_CHANGE)

# Errors a predicate/handler may raise that must not kill the poll loop.
_RULE_ERRORS = (OSError, RuntimeError, ValueError, AttributeError, TypeError,
                AutoControlException)
_UNSET = object()


@dataclass
class WatchRule:
    """Pair a predicate with the callback to fire on its transitions."""
    name: str
    predicate: Callable[[], Any]
    on_event: Callable[[str, Any], None]
    events: Sequence[str] = _ALL_EVENTS
    last: Any = _UNSET


def _transition(last: Any, value: Any) -> Optional[str]:
    """Classify the change from ``last`` to ``value`` as an event name."""
    now = bool(value)
    if last is _UNSET:
        return EVENT_APPEAR if now else None
    was = bool(last)
    if now and not was:
        return EVENT_APPEAR
    if was and not now:
        return EVENT_VANISH
    if now and was and value != last:
        return EVENT_CHANGE
    return None


class ScreenObserver:
    """Poll registered watches and fire callbacks on appear/vanish/change."""

    def __init__(self, poll_interval_s: float = 0.5) -> None:
        self._poll = max(0.05, float(poll_interval_s))
        self._rules: List[WatchRule] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._events: List[Dict[str, Any]] = []

    def add(self, name: str, predicate: Callable[[], Any],
            on_event: Callable[[str, Any], None], *,
            events: Optional[Sequence[str]] = None) -> WatchRule:
        """Register a watch; ``events`` defaults to all three transitions."""
        rule = WatchRule(name=name, predicate=predicate, on_event=on_event,
                         events=tuple(events) if events else _ALL_EVENTS)
        with self._lock:
            self._rules.append(rule)
        return rule

    def remove(self, name: str) -> bool:
        """Remove every watch with ``name``; return whether any matched."""
        with self._lock:
            before = len(self._rules)
            self._rules = [r for r in self._rules if r.name != name]
            return len(self._rules) < before

    def clear(self) -> None:
        """Remove all watches."""
        with self._lock:
            self._rules.clear()

    def names(self) -> List[str]:
        """Return the registered watch names."""
        with self._lock:
            return [rule.name for rule in self._rules]

    @property
    def running(self) -> bool:
        """Whether the background poll thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def fired(self) -> List[Dict[str, Any]]:
        """Log of fired events (``{rule, event, time}``)."""
        with self._lock:
            return list(self._events)

    def poll_once(self) -> List[Dict[str, Any]]:
        """Evaluate every watch once; fire callbacks and return the events."""
        with self._lock:
            rules = list(self._rules)
        return [event for event in (self._evaluate(rule) for rule in rules)
                if event is not None]

    def _evaluate(self, rule: WatchRule) -> Optional[Dict[str, Any]]:
        try:
            value = rule.predicate()
        except _RULE_ERRORS as error:
            autocontrol_logger.info(
                "observer %r predicate error: %r", rule.name, error)
            return None
        event = _transition(rule.last, value)
        rule.last = value
        if event is None or event not in rule.events:
            return None
        self._fire(rule, event, value)
        record = {"rule": rule.name, "event": event, "time": time.time()}
        with self._lock:
            self._events.append(record)
        return record

    def _fire(self, rule: WatchRule, event: str, value: Any) -> None:
        try:
            rule.on_event(event, value)
        except _RULE_ERRORS as error:
            autocontrol_logger.info(
                "observer %r handler error: %r", rule.name, error)

    def start(self) -> None:
        """Start the background poll thread (idempotent)."""
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="screen-observer", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the poll thread to stop and join it."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=float(timeout))
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self._poll)


def image_predicate(image: str, threshold: float = 0.8) -> Callable[[], Any]:
    """Predicate: the located image centre, or ``None`` when absent."""
    def predicate() -> Any:
        from je_auto_control.wrapper.auto_control_image import (
            locate_image_center)
        try:
            return locate_image_center(image, detect_threshold=float(threshold))
        except _RULE_ERRORS:
            return None
    return predicate


def text_predicate(text: str) -> Callable[[], Any]:
    """Predicate: the located text centre, or ``None`` when absent."""
    def predicate() -> Any:
        from je_auto_control.utils.ocr.ocr_engine import locate_text_center
        try:
            return locate_text_center(text)
        except _RULE_ERRORS:
            return None
    return predicate


def pixel_predicate(x: int, y: int) -> Callable[[], Any]:
    """Predicate: the RGB tuple at ``(x, y)`` — use with the 'change' event."""
    def predicate() -> Any:
        from je_auto_control.wrapper.auto_control_screen import get_pixel
        try:
            return tuple(get_pixel(int(x), int(y)))
        except _RULE_ERRORS:
            return None
    return predicate


default_observer = ScreenObserver()
