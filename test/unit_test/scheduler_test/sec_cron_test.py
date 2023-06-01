from je_auto_control import SchedulerManager


def test_scheduler():
    print("Test Scheduler")
    scheduler.remove_blocking_job(id="test")
    scheduler.shutdown_blocking_scheduler()


scheduler = SchedulerManager()
scheduler.add_cron_blocking(function=test_scheduler, id="test", second="*")
scheduler.start_block_scheduler()
