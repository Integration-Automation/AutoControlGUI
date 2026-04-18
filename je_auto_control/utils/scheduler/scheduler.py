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
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="AutoControlScheduler")
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            self._tick_once()
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
            self._fire(job, now_mono, now_wall)

    def _fire(self, job: ScheduledJob, now_mono: float, now_wall: float) -> None:
        run_id = default_history_store.start_run(
            SOURCE_SCHEDULER, job.job_id, job.script_path,
        )
        status = STATUS_OK
        error_text: Optional[str] = None
        try:
            actions = read_action_json(job.script_path)
            self._execute(actions)
        except (OSError, ValueError, RuntimeError) as error:
            status = STATUS_ERROR
            error_text = repr(error)
            autocontrol_logger.error("scheduler job %s failed: %r",
                                     job.job_id, error)
        finally:
            default_history_store.finish_run(run_id, status, error_text)
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
