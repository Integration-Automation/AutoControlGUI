"""Bind global hotkeys to JSON action files.

The daemon runs in a background thread, listening on the OS's
hotkey API. ``combo`` syntax matches the GUI's Hotkeys tab —
``ctrl+shift+f9`` style. Each binding points at a JSON action file
that the executor runs when the combo fires.
"""
import json
import time
from pathlib import Path

import je_auto_control as ac


SCRIPT = Path(__file__).with_name("on_hotkey.json")


def main() -> None:
    SCRIPT.write_text(
        json.dumps([
            ["AC_screenshot", {"file_path": "hotkey_capture.png"}],
        ]),
        encoding="utf-8",
    )

    daemon = ac.default_hotkey_daemon
    binding = daemon.bind("ctrl+shift+f9", str(SCRIPT))
    print(f"bound {binding.combo} → {binding.script_path}")

    daemon.start()
    print("daemon running — press Ctrl+Shift+F9 to capture, Ctrl-C here to stop.")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nstopping…")
    finally:
        daemon.stop()


if __name__ == "__main__":
    main()
