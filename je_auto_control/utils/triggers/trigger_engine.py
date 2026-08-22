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
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.run_history.artifact_manager import (
    capture_error_snapshot,
)
from je_auto_control.utils.run_history.history_store import (
    SOURCE_TRIGGER, STATUS_ERROR, STATUS_OK, default_history_store,
)

if TYPE_CHECKING:  # imported lazily at runtime, where each trigger needs it
    from je_auto_control.utils.scheduler.cron import CronExpression


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
        # locate_image_center raises ImageNotFoundException (an
        # AutoControlException) whenever the template is absent — the *normal*
        # case on most polls. Without the base in this tuple the exception
        # escaped to _is_fired_safely, which disables the trigger for good on
        # the first poll where the image isn't on screen yet.
        try:
            result = locate_image_center(self.image_path, self.threshold, False)
        except (OSError, RuntimeError, ValueError, AutoControlException):
            return False
        return result is not None


@dataclass
class WindowAppearsTrigger(_TriggerBase):
    """Fire when any open window title contains ``title_substring``."""
    title_substring: str = ""
    case_sensitive: bool = False

    def is_fired(self) -> bool:
        from je_auto_control.wrapper.auto_control_window import find_window
        # A framework error from the window backend must read as "not present
        # yet" (keep polling), never as a reason to permanently disable the
        # trigger in _is_fired_safely.
        try:
            return find_window(self.title_substring,
                               case_sensitive=self.case_sensitive) is not None
        except (OSError, RuntimeError, AutoControlException):
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
        # get_pixel can surface AutoControlScreenException from the backend;
        # treat it as "no match this poll" instead of letting it escape and
        # disable the trigger for good.
        try:
            raw = get_pixel(int(self.x), int(self.y))
        except (OSError, RuntimeError, ValueError, TypeError,
                AutoControlException):
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


@dataclass
class AllOfTrigger(_TriggerBase):
    """Fire when *every* child trigger's condition holds at the same poll."""
    children: List[_TriggerBase] = field(default_factory=list)

    def is_fired(self) -> bool:
        return bool(self.children) and all(
            child.is_fired() for child in self.children)


@dataclass
class AnyOfTrigger(_TriggerBase):
    """Fire when *any* child trigger's condition holds."""
    children: List[_TriggerBase] = field(default_factory=list)

    def is_fired(self) -> bool:
        return any(child.is_fired() for child in self.children)


@dataclass
class SequenceTrigger(_TriggerBase):
    """Fire once each child condition has held, in registration order.

    Children advance one step per poll, so the conditions must become true
    in sequence over time (not all at once). The step resets after firing.
    """
    children: List[_TriggerBase] = field(default_factory=list)
    _step: int = 0

    def is_fired(self) -> bool:
        if not self.children:
            return False
        if self._step >= len(self.children):
            self._step = 0
        if self.children[self._step].is_fired():
            self._step += 1
        if self._step >= len(self.children):
            self._step = 0
            return True
        return False


@dataclass
class CronTrigger(_TriggerBase):
    """Fire when the current local time matches a five-field cron expression.

    Fires at most once per matching minute (tracks the last-fired minute),
    so it composes cleanly with the boolean/sequence triggers — e.g.
    ``AllOfTrigger`` of a cron + an image trigger means "at 09:00 *and*
    only if the image is on screen".
    """
    cron: str = "* * * * *"
    _expr: Optional["CronExpression"] = None
    _last_minute: Optional[str] = None

    def __post_init__(self) -> None:
        # 在建構時就解析，讓錯誤的 cron 立刻在呼叫端炸出來，
        # 而不是等到輪詢執行緒才拋。
        # Parse eagerly so a bad expression fails at the caller (the Triggers
        # tab passes its text field straight through) instead of surfacing
        # later on the polling thread, where it used to kill every trigger.
        from je_auto_control.utils.scheduler.cron import parse_cron
        self._expr = parse_cron(self.cron)

    def is_fired(self) -> bool:
        import datetime as _dt
        from je_auto_control.utils.scheduler.cron import parse_cron
        if self._expr is None:
            self._expr = parse_cron(self.cron)
        now = _dt.datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        if minute_key == self._last_minute:
            return False
        if self._expr.matches(now):
            self._last_minute = minute_key
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
            if not self._is_fired_safely(trigger):
                continue
            try:
                self._fire(trigger, now)
            except Exception as error:  # noqa: BLE001  # reason: see below
                # _fire records its own execution errors, but its history
                # bookkeeping (start_run / finish_run) sits outside that
                # try. Nothing a single trigger does may stop the engine.
                trigger.enabled = False
                autocontrol_logger.error(
                    "trigger %s disabled after _fire() raised: %r",
                    trigger.trigger_id, error, exc_info=True,
                )

    def _is_fired_safely(self, trigger: _TriggerBase) -> bool:
        """Evaluate one trigger; never let it take the polling thread down.

        一個壞掉的 trigger 不能拖垮整個引擎。
        is_fired() reaches out to the screen, the filesystem, the clock — any
        of which can raise. Unguarded, one bad trigger killed the polling
        thread and silently stopped *every* registered trigger, and stayed
        registered so a restart died the same way. Disable the offender
        instead: it stops re-raising each tick and is visibly off in the UI.
        """
        try:
            return trigger.is_fired()
        except Exception as error:  # noqa: BLE001  # reason: see docstring
            trigger.enabled = False
            autocontrol_logger.error(
                "trigger %s disabled after is_fired() raised: %r",
                trigger.trigger_id, error, exc_info=True,
            )
            return False

    def _fire(self, trigger: _TriggerBase, now: float) -> None:
        run_id = default_history_store.start_run(
            SOURCE_TRIGGER, trigger.trigger_id, trigger.script_path,
        )
        status = STATUS_OK
        error_text: Optional[str] = None
        try:
            actions = read_action_json(trigger.script_path)
            self._execute(actions)
        # 這裡刻意攔截所有例外：一個 trigger 失敗必須記錄成 STATUS_ERROR
        # 並繼續，而不是拖垮輪詢執行緒。原本的 tuple 漏掉
        # AutoControlJsonActionException，所以光是改名 script 檔就會讓
        # 整個引擎永久停擺。
        # Deliberately broad: a failing trigger must be recorded as
        # STATUS_ERROR and the loop must go on — which the finally below
        # already assumes. The previous tuple (OSError, ValueError,
        # RuntimeError) missed AutoControlJsonActionException, so merely
        # renaming a trigger's script file killed the polling thread and
        # silently stopped every other trigger with it.
        except Exception as error:  # noqa: BLE001  # reason: see comment above
            status = STATUS_ERROR
            error_text = repr(error)
            autocontrol_logger.error("trigger %s failed: %r",
                                     trigger.trigger_id, error)
        finally:
            artifact = (capture_error_snapshot(run_id)
                        if status == STATUS_ERROR else None)
            default_history_store.finish_run(
                run_id, status, error_text, artifact_path=artifact,
            )
        with self._lock:
            live = self._triggers.get(trigger.trigger_id)
            if live is None:
                return
            live.fired += 1
            live._last_fire = now
            if not live.repeat:
                self._triggers.pop(trigger.trigger_id, None)


default_trigger_engine = TriggerEngine()
