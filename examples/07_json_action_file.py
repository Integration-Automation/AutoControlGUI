"""Execute the same JSON action file from Python and from the CLI.

The JSON format is the same one the GUI's recorder produces — every
command starts with ``AC_*`` and maps to a function in
``je_auto_control.utils.executor.action_executor``. The list runs
sequentially.
"""
import json
from pathlib import Path

import je_auto_control as ac


ACTION_FILE = Path(__file__).with_name("hello_world.json")


def main() -> None:
    actions = [
        {"command": "AC_screenshot", "file_path": "before.png"},
        {"command": "AC_set_mouse_position", "x": 100, "y": 100},
        {"command": "AC_click_mouse", "mouse_keycode": "mouse_left"},
        {"command": "AC_screenshot", "file_path": "after.png"},
    ]
    ACTION_FILE.write_text(json.dumps(actions, indent=2), encoding="utf-8")

    # Inline Python execution. ``execute_files`` takes a list of paths so
    # you can chain multiple action files in one call.
    ac.execute_files([str(ACTION_FILE)])

    # Equivalent CLI invocation:
    #   python -m je_auto_control.utils.executor.action_executor \
    #       --file hello_world.json
    print(f"executed {len(actions)} actions from {ACTION_FILE.name}")


if __name__ == "__main__":
    main()
