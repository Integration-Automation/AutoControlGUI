======
排程器
======

AutoControl 提供 `APScheduler <https://apscheduler.readthedocs.io/>`_ 的包裝，
用於排程重複性的自動化任務。

基本範例
========

.. code-block:: python

   from je_auto_control import SchedulerManager

   def my_task():
       print("任務已執行！")
       scheduler.remove_blocking_job(id="my_job")
       scheduler.shutdown_blocking_scheduler()

   scheduler = SchedulerManager()
   scheduler.add_interval_blocking_secondly(function=my_task, id="my_job")
   scheduler.start_block_scheduler()

阻塞與非阻塞模式
=================

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 模式
     - 說明
   * - 阻塞 (Blocking)
     - ``start_block_scheduler()`` 會阻塞目前的執行緒。適用於獨立的排程腳本。
   * - 非阻塞 (Non-blocking)
     - ``start_nonblocking_scheduler()`` 在背景執行緒中執行。適用於主執行緒需要處理其他工作的情況。

間隔排程
========

以固定間隔執行函式：

.. code-block:: python

   # 每秒
   scheduler.add_interval_blocking_secondly(function=my_task, id="job1")

   # 每分鐘
   scheduler.add_interval_blocking_minutely(function=my_task, id="job2")

   # 每小時
   scheduler.add_interval_blocking_hourly(function=my_task, id="job3")

   # 每天
   scheduler.add_interval_blocking_daily(function=my_task, id="job4")

   # 每週
   scheduler.add_interval_blocking_weekly(function=my_task, id="job5")

非阻塞版本可使用 ``add_interval_nonblocking_*`` 系列方法。

Cron 排程
=========

.. code-block:: python

   scheduler.add_cron_blocking(function=my_task, id="cron_job", hour=9, minute=30)

移除任務
========

.. code-block:: python

   scheduler.remove_blocking_job(id="job1")
   scheduler.remove_nonblocking_job(id="job2")

關閉排程器
==========

.. code-block:: python

   scheduler.shutdown_blocking_scheduler()
   scheduler.shutdown_nonblocking_scheduler()

.. tip::

   完整 API 參考請見 :doc:`/API/utils/scheduler`。
