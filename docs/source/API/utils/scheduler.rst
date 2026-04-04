=============
Scheduler API
=============

The ``SchedulerManager`` class wraps APScheduler for scheduling automation tasks.

----

SchedulerManager
================

.. class:: SchedulerManager

   Manages blocking and non-blocking schedulers.

   Adding Jobs
   -----------

   .. method:: add_blocking_job(func, trigger=None, args=None, kwargs=None, id=None, name=None, misfire_grace_time=undefined, coalesce=undefined, max_instances=undefined, next_run_time=undefined, jobstore='default', executor='default', replace_existing=False, **trigger_args)

      Adds a job to the blocking scheduler. Wraps APScheduler's ``add_job()``.

      :param callable func: Function to run.
      :param str trigger: Trigger type (e.g., ``"interval"``, ``"cron"``).
      :param str id: Unique job identifier.
      :param str name: Human-readable job name.
      :param bool replace_existing: If ``True``, replaces a job with the same ``id``.
      :returns: The created Job instance.
      :rtype: Job

   .. method:: add_nonblocking_job(func, trigger=None, args=None, kwargs=None, id=None, name=None, **trigger_args)

      Adds a job to the non-blocking (background) scheduler. Same parameters as ``add_blocking_job()``.

   Interval Scheduling
   -------------------

   Convenience methods for interval-based scheduling. All accept ``function``, ``id``, ``args``, ``kwargs``, and the interval parameter.

   **Blocking:**

   .. method:: add_interval_blocking_secondly(function, id=None, seconds=1, **trigger_args)
   .. method:: add_interval_blocking_minutely(function, id=None, minutes=1, **trigger_args)
   .. method:: add_interval_blocking_hourly(function, id=None, hours=1, **trigger_args)
   .. method:: add_interval_blocking_daily(function, id=None, days=1, **trigger_args)
   .. method:: add_interval_blocking_weekly(function, id=None, weeks=1, **trigger_args)

   **Non-blocking:**

   .. method:: add_interval_nonblocking_secondly(function, id=None, seconds=1, **trigger_args)
   .. method:: add_interval_nonblocking_minutely(function, id=None, minutes=1, **trigger_args)
   .. method:: add_interval_nonblocking_hourly(function, id=None, hours=1, **trigger_args)
   .. method:: add_interval_nonblocking_daily(function, id=None, days=1, **trigger_args)
   .. method:: add_interval_nonblocking_weekly(function, id=None, weeks=1, **trigger_args)

   Cron Scheduling
   ---------------

   .. method:: add_cron_blocking(function, id=None, **trigger_args)

      Adds a cron-triggered job to the blocking scheduler.

   .. method:: add_cron_nonblocking(function, id=None, **trigger_args)

      Adds a cron-triggered job to the non-blocking scheduler.

   Scheduler Control
   -----------------

   .. method:: get_blocking_scheduler()

      :returns: The blocking scheduler instance.
      :rtype: BlockingScheduler

   .. method:: get_nonblocking_scheduler()

      :returns: The background scheduler instance.
      :rtype: BackgroundScheduler

   .. method:: start_block_scheduler(*args, **kwargs)

      Starts the blocking scheduler (blocks the current thread).

   .. method:: start_nonblocking_scheduler(*args, **kwargs)

      Starts the non-blocking scheduler in a background thread.

   .. method:: start_all_scheduler(*args, **kwargs)

      Starts both blocking and non-blocking schedulers.

   Job Management
   --------------

   .. method:: remove_blocking_job(id, jobstore='default')

      Removes a job from the blocking scheduler.

      :param str id: Job identifier.

   .. method:: remove_nonblocking_job(id, jobstore='default')

      Removes a job from the non-blocking scheduler.

      :param str id: Job identifier.

   .. method:: shutdown_blocking_scheduler(wait=False)

      Shuts down the blocking scheduler.

      :param bool wait: If ``True``, waits for running jobs to finish.

   .. method:: shutdown_nonblocking_scheduler(wait=False)

      Shuts down the non-blocking scheduler.

      :param bool wait: If ``True``, waits for running jobs to finish.
