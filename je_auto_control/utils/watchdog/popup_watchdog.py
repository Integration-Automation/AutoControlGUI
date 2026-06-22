"""Background popup/interrupt watchdog.

The #1 reason unattended automation fails is an unexpected dialog the
script was never coded for — a UAC prompt, "session expiring", a Windows
Update toast, a newsletter modal. This watchdog runs a concurrent guard
thread that polls for registered patterns and dismisses them (or runs a
recovery handler) *independently* of the main step sequence, so the flow
keeps going.

It is deliberately generic: a :class:`WatchdogRule` pairs a ``matcher``
(is the popup present?) with an ``action`` (dismiss it). Convenience
constructors build window-title rules from the window wrapper; both are
injectable so the logic is unit-tested without a real desktop. Imports no
``PySide6`` — fully headless.
"""
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

# Errors a rule's matcher/action may raise that must not kill the guard loop
# (e.g. find_window raising AutoControlException off Windows).
_RULE_ERRORS = (OSError, RuntimeError, ValueError, AttributeError, TypeError,
                AutoControlException)


@dataclass
class WatchdogRule:
    """Pair a popup detector with the action that dismisses it."""
    name: str
    matcher: Callable[[], bool]
    action: Callable[[], None]


class PopupWatchdog:
    """Poll for registered popups on a background thread and dismiss them."""

    def __init__(self, poll_interval_s: float = 1.0) -> None:
        self._poll = max(0.05, float(poll_interval_s))
        self._rules: List[WatchdogRule] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._hits: List[Dict[str, Any]] = []

    def add_rule(self, rule: WatchdogRule) -> None:
        """Register a generic detector/dismisser rule."""
        with self._lock:
            self._rules.append(rule)

    def add_window_rule(self, title: str, *, action: str = "close",
                        case_sensitive: bool = False,
                        name: Optional[str] = None) -> None:
        """Register a rule that dismisses a window matching ``title``.

        ``action`` is ``"close"`` (close the window) or a key name to press
        (e.g. ``"enter"`` / ``"esc"``).
        """
        rule = WatchdogRule(
            name=name or f"window:{title}",
            matcher=_window_matcher(title, case_sensitive),
            action=_window_action(title, action, case_sensitive),
        )
        self.add_rule(rule)

    def clear(self) -> None:
        """Remove all rules."""
        with self._lock:
            self._rules.clear()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def hits(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._hits)

    def rule_names(self) -> List[str]:
        with self._lock:
            return [rule.name for rule in self._rules]

    def start(self) -> None:
        """Start the guard thread (idempotent)."""
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="rd-popup-watchdog", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the guard thread to stop and join it."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=float(timeout))
        self._thread = None

    def check_once(self) -> int:
        """Run one detection pass; return the number of popups dismissed."""
        dismissed = 0
        with self._lock:
            rules = list(self._rules)
        for rule in rules:
            if self._apply(rule):
                dismissed += 1
        return dismissed

    def _apply(self, rule: WatchdogRule) -> bool:
        try:
            if not rule.matcher():
                return False
            rule.action()
        except _RULE_ERRORS as error:
            autocontrol_logger.info(
                "popup watchdog rule %r error: %r", rule.name, error)
            return False
        with self._lock:
            self._hits.append({"rule": rule.name, "time": time.time()})
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.check_once()
            self._stop.wait(self._poll)


def _window_matcher(title: str, case_sensitive: bool) -> Callable[[], bool]:
    def present() -> bool:
        from je_auto_control.wrapper.auto_control_window import find_window
        return find_window(title, case_sensitive=case_sensitive) is not None
    return present


def _window_action(title: str, action: str,
                   case_sensitive: bool) -> Callable[[], None]:
    if action == "close":
        def close() -> None:
            from je_auto_control.wrapper.auto_control_window import (
                close_window_by_title,
            )
            close_window_by_title(title, case_sensitive=case_sensitive)
        return close

    def press_key() -> None:
        from je_auto_control.wrapper.auto_control_keyboard import type_keyboard
        type_keyboard(action)
    return press_key


default_popup_watchdog = PopupWatchdog()
