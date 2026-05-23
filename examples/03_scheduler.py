"""Run a JSON action file every 30 s from the headless scheduler."""
import time
from pathlib import Path

import je_auto_control as ac


def main() -> None:
    actions_path = Path(__file__).with_name("hello.json")
    actions_path.write_text(
        '[{"command": "AC_screenshot", "file_path": "scheduled.png"}]',
        encoding="utf-8",
    )

    scheduler = ac.default_scheduler()
    job = scheduler.add_job(
        script_path=str(actions_path),
        interval_seconds=30.0,
        job_id="hello-screenshots",
    )
    scheduler.start()
    print(f"scheduler started — job {job.job_id} fires every "
          f"{job.interval_seconds:.0f}s. Ctrl-C stops cleanly.")

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nshutting down…")
    finally:
        scheduler.stop()


if __name__ == "__main__":
    main()
