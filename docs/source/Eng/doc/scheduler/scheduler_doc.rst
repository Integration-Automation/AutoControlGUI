Scheduler
----

You can use scheduling to perform repetitive tasks, either by using a simple wrapper for APScheduler or by consulting the API documentation to use it yourself.

.. code-block:: python

    from je_web_runner import SchedulerManager


    def test_scheduler():
        print("Test Scheduler")
        scheduler.remove_blocking_job(id="test")
        scheduler.shutdown_blocking_scheduler()


    scheduler = SchedulerManager()
    scheduler.add_interval_blocking_secondly(function=test_scheduler, id="test")
    scheduler.start_block_scheduler()
