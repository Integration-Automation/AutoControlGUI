"""Poll-based trigger engine.

Each trigger implements ``is_fired()`` and an action JSON path to execute
when the condition is met. A single background thread polls all active
triggers and invokes the executor when any fires.

Triggers fire at most once by default — set ``repeat=True`` to re-arm
after each firing.
"""
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


@dataclass
class _TriggerBase:
    """Shared fields / behaviour for all triggers."""
    trigger_id: str
    script_path: str
    repeat: bool = False
    enabled: bool = True
    fired: int = 0
    cooldown_seconds: float = 0.5
    _last_fire: float = field(default=0.0)

    def is_fired(self) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError

    def should_poll(self, now: float) -> bool:
        return self.enabled and (now - self._last_fire) >= self.cooldown_seconds


@dataclass
class ImageAppearsTrigger(_TriggerBase):
    """Fire when the template ``image_path`` is found on screen."""
    image_path: str = ""
    threshold: float = 0.8

    def is_fired(self) -> bool:
        from je_auto_control.wrapper.auto_control_image import locate_image_center
        try:
            result = locate_image_center(self.image_path, self.threshold, False)
        except (OSError, RuntimeError, ValueError):
            return False
        return result is not None


@dataclass
class WindowAppearsTrigger(_TriggerBase):
    """Fire when any open window title contains ``title_substring``."""
    title_substring: str = ""
    case_sensitive: bool = False

    def is_fired(self) -> bool:
        from je_auto_control.wrapper.auto_control_window import find_window
        try:
            return find_window(self.title_substring,
                               case_sensitive=self.case_sensitive) is not None
        except (NotImplementedError, OSError, RuntimeError):
            return False


@dataclass
class PixelColorTrigger(_TriggerBase):
    """Fire when pixel at ``(x, y)`` matches ``target_rgb`` within tolerance."""
    x: int = 0
    y: int = 0
    target_rgb: Tuple[int, int, int] = (0, 0, 0)
    tolerance: int = 8

    def is_fired(self) -> bool:
        from je_auto_control.wrapper.auto_control_screen import get_pixel
        try:
            raw = get_pixel(int(self.x), int(self.y))
        except (OSError, RuntimeError, ValueError, TypeError):
            return False
        if raw is None or len(raw) < 3:
            return False
        return all(abs(int(raw[i]) - int(self.target_rgb[i])) <= self.tolerance
                   for i in range(3))


@dataclass
class FilePathTrigger(_TriggerBase):
    """Fire when ``watch_path`` mtime changes (created or modified)."""
    watch_path: str = ""
    _baseline: Optional[float] = None

    def is_fired(self) -> bool:
        try:
            mtime = os.path.getmtime(self.watch_path)
        except OSError:
            return False
        if self._baseline is None:
            self._baseline = mtime
            return False
        if mtime > self._baseline:
            self._baseline = mtime
            return True
        return False


class TriggerEngine:
    """Polls registered triggers on a background thread."""

    def __init__(self, executor: Optional[Callable[[list], object]] = None,
                 tick_seconds: float = 0.25) -> None:
        from je_auto_control.utils.executor.action_executor import execute_action
        self._execute = executor or execute_action
        self._tick = max(0.05, float(tick_seconds))
        self._triggers: Dict[str, _TriggerBase] = {}
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def add(self, trigger: _TriggerBase) -> _TriggerBase:
        """Register ``trigger``; assigns an id when missing."""
        if not trigger.trigger_id:
            trigger.trigger_id = uuid.uuid4().hex[:8]
        with self._lock:
            self._triggers[trigger.trigger_id] = trigger
        return trigger

    def remove(self, trigger_id: str) -> bool:
        with self._lock:
            return self._triggers.pop(trigger_id, None) is not None

    def list_triggers(self) -> List[_TriggerBase]:
        with self._lock:
            return list(self._triggers.values())

    def set_enabled(self, trigger_id: str, enabled: bool) -> bool:
        with self._lock:
            trigger = self._triggers.get(trigger_id)
            if trigger is None:
                return False
            trigger.enabled = bool(enabled)
            return True

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="AutoControlTriggers",
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            self._poll_once()
            self._stop.wait(self._tick)

    def _poll_once(self) -> None:
        now = time.monotonic()
        with self._lock:
            candidates = [t for t in self._triggers.values()
                          if t.should_poll(now)]
        for trigger in candidates:
            if not trigger.is_fired():
                continue
            self._fire(trigger, now)

    def _fire(self, trigger: _TriggerBase, now: float) -> None:
        try:
            actions = read_action_json(trigger.script_path)
            self._execute(actions)
        except (OSError, ValueError, RuntimeError) as error:
            autocontrol_logger.error("trigger %s failed: %r",
                                     trigger.trigger_id, error)
        with self._lock:
            live = self._triggers.get(trigger.trigger_id)
            if live is None:
                return
            live.fired += 1
            live._last_fire = now
            if not live.repeat:
                self._triggers.pop(trigger.trigger_id, None)


default_trigger_engine = TriggerEngine()
