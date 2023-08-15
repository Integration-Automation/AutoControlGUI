Scheduler
----

可以使用排程來執行重複的任務，可以使用對 APScheduler 的簡易包裝或是觀看 API 文件自行使用

.. code-block:: python

    from je_web_runner import SchedulerManager


    def test_scheduler():
        print("Test Scheduler")
        scheduler.remove_blocking_job(id="test")
        scheduler.shutdown_blocking_scheduler()


    scheduler = SchedulerManager()
    scheduler.add_interval_blocking_secondly(function=test_scheduler, id="test")
    scheduler.start_block_scheduler()
