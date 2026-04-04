=========
Scheduler
=========

AutoControl provides a wrapper around `APScheduler <https://apscheduler.readthedocs.io/>`_ for
scheduling repetitive automation tasks.

Basic Example
=============

.. code-block:: python

   from je_auto_control import SchedulerManager

   def my_task():
       print("Task executed!")
       scheduler.remove_blocking_job(id="my_job")
       scheduler.shutdown_blocking_scheduler()

   scheduler = SchedulerManager()
   scheduler.add_interval_blocking_secondly(function=my_task, id="my_job")
   scheduler.start_block_scheduler()

Blocking vs Non-Blocking
=========================

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Mode
     - Description
   * - Blocking
     - ``start_block_scheduler()`` blocks the current thread. Use for standalone scheduler scripts.
   * - Non-blocking
     - ``start_nonblocking_scheduler()`` runs in a background thread. Use when you need the main thread for other work.

Interval Scheduling
===================

Schedule a function to run at fixed intervals:

.. code-block:: python

   # Every second
   scheduler.add_interval_blocking_secondly(function=my_task, id="job1")

   # Every minute
   scheduler.add_interval_blocking_minutely(function=my_task, id="job2")

   # Every hour
   scheduler.add_interval_blocking_hourly(function=my_task, id="job3")

   # Every day
   scheduler.add_interval_blocking_daily(function=my_task, id="job4")

   # Every week
   scheduler.add_interval_blocking_weekly(function=my_task, id="job5")

Non-blocking equivalents are available with ``add_interval_nonblocking_*`` methods.

Cron Scheduling
===============

.. code-block:: python

   scheduler.add_cron_blocking(function=my_task, id="cron_job", hour=9, minute=30)

Removing Jobs
=============

.. code-block:: python

   scheduler.remove_blocking_job(id="job1")
   scheduler.remove_nonblocking_job(id="job2")

Shutting Down
=============

.. code-block:: python

   scheduler.shutdown_blocking_scheduler()
   scheduler.shutdown_nonblocking_scheduler()

.. tip::

   See the :doc:`/API/utils/scheduler` for the complete API reference.
