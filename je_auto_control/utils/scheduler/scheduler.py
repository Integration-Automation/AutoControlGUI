"""Thread-based scheduler for repeated or delayed execution of action JSON files.

Not a full cron — intentionally minimal: one-shot (run after N seconds) and
repeating (run every N seconds, optionally with a maximum run count).
"""
import datetime as _dt
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.run_history.artifact_manager import (
    capture_error_snapshot,
)
from je_auto_control.utils.run_history.history_store import (
    SOURCE_SCHEDULER, STATUS_ERROR, STATUS_OK, default_history_store,
)
from je_auto_control.utils.scheduler.cron import (
    CronExpression, next_match, parse_cron,
)


@dataclass
class ScheduledJob:
    """One scheduled execution entry.

    Either ``interval_seconds`` OR ``cron_expression`` drives firing — never both.

    :param job_id: unique identifier; auto-generated if empty.
    :param script_path: path to an action JSON file to execute.
    :param interval_seconds: delay before first run + between repeats (interval mode).
    :param cron_expression: parsed cron rule (cron mode); ``None`` for interval jobs.
    :param repeat: if False, run once then remove the job (interval mode only).
    :param max_runs: optional cap on total runs (None = unlimited).
    :param runs: number of times this job has executed.
    :param enabled: paused jobs stay registered but skip firing.
    :param next_run_ts: monotonic deadline (interval) or wall-clock epoch (cron).
    """
    job_id: str
    script_path: str
    interval_seconds: float = 0.0
    cron_expression: Optional[CronExpression] = None
    repeat: bool = True
    max_runs: Optional[int] = None
    runs: int = 0
    enabled: bool = True
    next_run_ts: float = field(default=0.0)

    @property
    def is_cron(self) -> bool:
        return self.cron_expression is not None


class Scheduler:
    """Thread-safe scheduler that polls jobs on a background thread."""

    def __init__(self, executor: Optional[Callable[[list], object]] = None,
                 tick_seconds: float = 0.5) -> None:
        from je_auto_control.utils.executor.action_executor import execute_action
        self._execute = executor or execute_action
        self._tick = max(0.1, float(tick_seconds))
        self._jobs: Dict[str, ScheduledJob] = {}
        self._lock = threading.Lock()
        # 保護 start()/stop() 互斥。兩者原本毫無互斥,交錯時 stop() 會在
        # start() 指派 _thread 與呼叫 .start() 之間 join 尚未啟動的執行緒
        # → RuntimeError("cannot join thread before it is started")。與
        # _lock(工作註冊表)分開,且為最外層鎖。
        # Serialises start() against stop(). Nothing enforced it before: an
        # interleaved stop() joined the thread between start()'s assignment and
        # its .start() call → "cannot join thread before it is started". Kept
        # separate from _lock (the job registry) and taken as the outermost.
        self._lifecycle_lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def add_job(self, script_path: str, interval_seconds: float,
                repeat: bool = True, max_runs: Optional[int] = None,
                job_id: Optional[str] = None) -> ScheduledJob:
        """Register and schedule a new interval job; return the record."""
        jid = job_id or uuid.uuid4().hex[:8]
        now = time.monotonic()
        interval = max(0.1, float(interval_seconds))
        job = ScheduledJob(
            job_id=jid, script_path=script_path,
            interval_seconds=interval,
            repeat=repeat, max_runs=max_runs,
            next_run_ts=now + interval,
        )
        with self._lock:
            self._jobs[jid] = job
        autocontrol_logger.info("scheduler add_job %s %s", jid, script_path)
        return job

    def add_cron_job(self, script_path: str, cron_expression: str,
                     max_runs: Optional[int] = None,
                     job_id: Optional[str] = None) -> ScheduledJob:
        """Register a cron-driven job (5-field expression)."""
        expression = parse_cron(cron_expression)
        jid = job_id or uuid.uuid4().hex[:8]
        now_wall = _dt.datetime.now()
        next_at = next_match(expression, now_wall)
        job = ScheduledJob(
            job_id=jid, script_path=script_path,
            interval_seconds=0.0,
            cron_expression=expression,
            repeat=True, max_runs=max_runs,
            next_run_ts=next_at.timestamp(),
        )
        with self._lock:
            self._jobs[jid] = job
        autocontrol_logger.info("scheduler add_cron_job %s %r -> %s",
                                jid, cron_expression, next_at.isoformat())
        return job

    def remove_job(self, job_id: str) -> bool:
        with self._lock:
            return self._jobs.pop(job_id, None) is not None

    def set_enabled(self, job_id: str, enabled: bool) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.enabled = bool(enabled)
            return True

    def list_jobs(self) -> List[ScheduledJob]:
        with self._lock:
            return list(self._jobs.values())

    def start(self) -> None:
        """Start the polling thread if it is not already running."""
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="AutoControlScheduler")
            self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        with self._lifecycle_lock:
            self._stop.set()
            thread = self._thread
            if thread is not None and thread.is_alive():
                thread.join(timeout=timeout)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            # Outer guard: _tick_once must never let anything escape and take
            # the scheduler thread (hence every job) down.
            try:
                self._tick_once()
            except Exception as error:  # noqa: BLE001  # reason: see above
                autocontrol_logger.error("scheduler tick failed: %r",
                                         error, exc_info=True)
            self._stop.wait(self._tick)

    def _tick_once(self) -> None:
        now_mono = time.monotonic()
        now_wall = time.time()
        due: List[ScheduledJob] = []
        with self._lock:
            for job in self._jobs.values():
                if not job.enabled:
                    continue
                deadline_now = now_wall if job.is_cron else now_mono
                if deadline_now >= job.next_run_ts:
                    due.append(job)
        for job in due:
            # _fire's run-history bookkeeping (start_run / capture_error_snapshot
            # / finish_run) and its cron re-scheduling sit OUTSIDE its own broad
            # except. A sqlite3.Error from the shared history DB, or an
            # AutoControlScreenException while snapshotting, would otherwise kill
            # this loop and stop every scheduled job. Contain per job.
            try:
                self._fire(job, now_mono, now_wall)
            except Exception as error:  # noqa: BLE001  # reason: see above
                autocontrol_logger.error("scheduler job %s bookkeeping "
                                         "failed: %r", job.job_id, error,
                                         exc_info=True)

    def _fire(self, job: ScheduledJob, now_mono: float, now_wall: float) -> None:
        run_id = default_history_store.start_run(
            SOURCE_SCHEDULER, job.job_id, job.script_path,
        )
        status = STATUS_OK
        error_text: Optional[str] = None
        try:
            actions = read_action_json(job.script_path)
            self._execute(actions)
        # 一個排程工作失敗必須記錄為 STATUS_ERROR 並繼續輪詢,絕不能拖垮
        # 排程執行緒。原本的 tuple 漏掉 AutoControlException——它是幾乎所有
        # action 失敗(找不到視窗/圖片、輸入錯誤)的基底,直接繼承
        # Exception,不屬 OSError/ValueError/RuntimeError——所以任何正常失敗
        # 的排程工作都會讓執行緒無聲死亡,其餘所有排程從此停擺。
        # A failing scheduled job must be recorded as STATUS_ERROR and the loop
        # must go on — it must never kill the scheduler thread. The previous
        # tuple missed AutoControlException, the base of nearly every action
        # failure (window/image not found, input error) and a direct Exception
        # subclass, so any normally-failing job killed the thread silently and
        # every other scheduled job stopped firing forever.
        except Exception as error:  # noqa: BLE001  # reason: see comment above
            status = STATUS_ERROR
            error_text = repr(error)
            autocontrol_logger.error("scheduler job %s failed: %r",
                                     job.job_id, error)
        finally:
            artifact = (capture_error_snapshot(run_id)
                        if status == STATUS_ERROR else None)
            default_history_store.finish_run(
                run_id, status, error_text, artifact_path=artifact,
            )
        with self._lock:
            live = self._jobs.get(job.job_id)
            if live is None:
                return
            live.runs += 1
            if live.max_runs is not None and live.runs >= live.max_runs:
                self._jobs.pop(job.job_id, None)
                return
            if live.is_cron:
                next_dt = next_match(live.cron_expression,
                                     _dt.datetime.fromtimestamp(now_wall))
                live.next_run_ts = next_dt.timestamp()
                return
            if not live.repeat:
                self._jobs.pop(job.job_id, None)
                return
            live.next_run_ts = now_mono + live.interval_seconds


default_scheduler = Scheduler()
