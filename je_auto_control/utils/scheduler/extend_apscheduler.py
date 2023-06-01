from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.util import undefined


class SchedulerManager(object):

    def __init__(self):
        self._blocking_schedulers: BlockingScheduler = BlockingScheduler()
        self._background_schedulers: BackgroundScheduler = BackgroundScheduler()

    def add_blocking_job(
            self, func, trigger=None, args=None, kwargs=None, id=None, name=None,
            misfire_grace_time=undefined, coalesce=undefined, max_instances=undefined,
            next_run_time=undefined, jobstore='default', executor='default',
            replace_existing=False, **trigger_args):
        params = locals()
        params.pop("self")
        trigger_args = params.pop("trigger_args")
        self._blocking_schedulers.add_job(**params, **trigger_args)

    def add_nonblocking_job(
            self, func, trigger=None, args=None, kwargs=None, id=None, name=None,
            misfire_grace_time=undefined, coalesce=undefined, max_instances=undefined,
            next_run_time=undefined, jobstore='default', executor='default',
            replace_existing=False, **trigger_args):
        params = locals()
        params.pop("self")
        trigger_args = params.pop("trigger_args")
        self._background_schedulers.add_job(**params, **trigger_args)

    def get_blocking_scheduler(self):
        return self._blocking_schedulers

    def get_nonblocking_scheduler(self):
        return self._background_schedulers

    def start_block_scheduler(self, *args, **kwargs):
        self._blocking_schedulers.start(*args, **kwargs)

    def start_nonblocking_scheduler(self, *args, **kwargs):
        self._background_schedulers.start(*args, **kwargs)

    def start_all_scheduler(self, *args, **kwargs):
        self._blocking_schedulers.start(*args, **kwargs)
        self._background_schedulers.start(*args, **kwargs)

    def add_interval_blocking_secondly(
            self, function: Callable, id: str = None, args: list = None,
            kwargs: dict = None, seconds: int = 1, **trigger_args):
        self.add_blocking_job(
            func=function, trigger="interval", id=id, args=args, kwargs=kwargs, seconds=seconds, **trigger_args)

    def add_interval_blocking_minutely(
            self, function: Callable, id: str = None, args: list = None,
            kwargs: dict = None, minutes: int = 1, **trigger_args):
        self.add_blocking_job(
            func=function, trigger="interval", id=id, args=args, kwargs=kwargs, minutes=minutes, **trigger_args)

    def add_interval_blocking_hourly(
            self, function: Callable, id: str = None, args: list = None,
            kwargs: dict = None, hours: int = 1, **trigger_args):
        self.add_blocking_job(
            func=function, trigger="interval", id=id, args=args, kwargs=kwargs, hours=hours, **trigger_args)

    def add_interval_blocking_daily(
            self, function: Callable, id: str = None, args: list = None,
            kwargs: dict = None, days: int = 1, **trigger_args):
        self.add_blocking_job(
            func=function, trigger="interval", id=id, args=args, kwargs=kwargs, days=days, **trigger_args)

    def add_interval_blocking_weekly(
            self, function: Callable, id: str = None, args: list = None,
            kwargs: dict = None, weeks: int = 1, **trigger_args):
        self.add_blocking_job(
            func=function, trigger="interval", id=id, args=args, kwargs=kwargs, weeks=weeks, **trigger_args)

    def add_interval_nonblocking_secondly(
            self, function: Callable, id: str = None, args: list = None,
            kwargs: dict = None, seconds: int = 1, **trigger_args):
        self.add_nonblocking_job(
            func=function, trigger="interval", id=id, args=args, kwargs=kwargs, seconds=seconds, **trigger_args)

    def add_interval_nonblocking_minutely(
            self, function: Callable, id: str = None, args: list = None,
            kwargs: dict = None, minutes: int = 1, **trigger_args):
        self.add_nonblocking_job(
            func=function, trigger="interval", id=id, args=args, kwargs=kwargs, minutes=minutes, **trigger_args)

    def add_interval_nonblocking_hourly(
            self, function: Callable, id: str = None, args: list = None,
            kwargs: dict = None, hours: int = 1, **trigger_args):
        self.add_nonblocking_job(
            func=function, trigger="interval", id=id, args=args, kwargs=kwargs, hours=hours, **trigger_args)

    def add_interval_nonblocking_daily(
            self, function: Callable, id: str = None, args: list = None,
            kwargs: dict = None, days: int = 1, **trigger_args):
        self.add_nonblocking_job(
            func=function, trigger="interval", id=id, args=args, kwargs=kwargs, days=days, **trigger_args)

    def add_interval_nonblocking_weekly(
            self, function: Callable, id: str = None, args: list = None,
            kwargs: dict = None, weeks: int = 1, **trigger_args):
        self.add_nonblocking_job(
            func=function, trigger="interval", id=id, args=args, kwargs=kwargs, weeks=weeks, **trigger_args)

    def add_cron_blocking(
            self, function: Callable, id: str = None, **trigger_args):
        self.add_blocking_job(func=function, id=id, trigger="cron", **trigger_args)

    def add_cron_nonblocking(
            self, function: Callable, id: str = None, **trigger_args):
        self.add_nonblocking_job(func=function, id=id, trigger="cron", **trigger_args)

    def remove_blocking_job(self, id: str, jobstore: str = 'default'):
        self._blocking_schedulers.remove_job(job_id=id, jobstore=jobstore)

    def remove_nonblocking_job(self, id: str, jobstore: str = 'default'):
        self._background_schedulers.remove_job(job_id=id, jobstore=jobstore)

    def shutdown_blocking_scheduler(self, wait: bool = False):
        self._blocking_schedulers.shutdown(wait=wait)

    def shutdown_nonblocking_scheduler(self, wait: bool = False):
        self._background_schedulers.shutdown(wait=wait)
