"""Auto-run a JSON action file when a template image appears on screen.

The trigger engine polls every ``tick_seconds`` and fires the bound
script whenever ``ImageAppearsTrigger.is_fired()`` returns True.

A practical use case: watch for a popup dialog template and dismiss it
without manual intervention.
"""
import json
import time
from pathlib import Path

import je_auto_control as ac


SCRIPT = Path(__file__).with_name("dismiss_popup.json")


def main() -> None:
    SCRIPT.write_text(
        json.dumps([
            ["AC_screenshot", {"file_path": "popup_seen.png"}],
        ]),
        encoding="utf-8",
    )

    engine = ac.default_trigger_engine
    trigger = engine.add(ac.ImageAppearsTrigger(
        trigger_id="",                       # auto-generated
        script_path=str(SCRIPT),
        image_path="popup_template.png",     # crop the popup beforehand
        threshold=0.85,
        cooldown_seconds=2.0,
        repeat=True,
    ))
    engine.start()
    print(f"trigger {trigger.trigger_id!r} watching for popup_template.png")
    print("Ctrl-C to stop.")

    try:
        while True:
            time.sleep(1.0)
            print(f"  fired {trigger.fired}x so far")
    except KeyboardInterrupt:
        print("\nstopping…")
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
