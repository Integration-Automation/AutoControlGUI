"""Record real user input, save it as JSON, then replay it.

Press Ctrl-C inside the terminal (or close the recorder window in the
GUI version) to stop. The captured list is exactly the format the
executor expects, so you can keep it forever and replay any time.
"""
import json
import time
from pathlib import Path

import je_auto_control as ac


RECORDING_PATH = Path(__file__).with_name("my_recording.json")


def main() -> None:
    print("recording 5 s of mouse + keyboard input — interact with the screen")
    ac.record()
    try:
        time.sleep(5.0)
    finally:
        captured = ac.stop_record()

    RECORDING_PATH.write_text(
        json.dumps(captured, indent=2), encoding="utf-8",
    )
    print(f"saved {len(captured)} actions to {RECORDING_PATH}")

    print("replaying…")
    ac.execute_files([str(RECORDING_PATH)])
    print("done")


if __name__ == "__main__":
    main()
