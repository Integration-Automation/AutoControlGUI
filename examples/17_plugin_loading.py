"""Load extra ``AC_*`` commands from a plugin file and call them.

The plugin file can ship in any pip-installable package; it only
needs to define functions whose names start with ``AC_``. They land
in the same executor that drives JSON action files, so they're
immediately usable from scripts, the socket server, the scheduler,
and the visual builder.
"""
import json
from pathlib import Path

import je_auto_control as ac


PLUGIN_PATH = Path(__file__).with_name("my_plugin.py")
ACTION_PATH = Path(__file__).with_name("uses_plugin.json")


def main() -> None:
    PLUGIN_PATH.write_text(
        '"""Tiny plugin that adds two new AC_* commands."""\n'
        '\n'
        '\n'
        'def AC_say_hello(name="world"):\n'
        '    print(f"hello, {name}!")\n'
        '    return {"greeted": name}\n'
        '\n'
        '\n'
        'def AC_double(value):\n'
        '    return value * 2\n',
        encoding="utf-8",
    )

    commands = ac.load_plugin_file(str(PLUGIN_PATH))
    registered = ac.register_plugin_commands(commands)
    print(f"registered: {registered}")

    # The new commands are now first-class — drive them from a JSON action.
    actions = [
        ["AC_say_hello", {"name": "AutoControl user"}],
        ["AC_double",    {"value": 21}],
    ]
    ACTION_PATH.write_text(
        json.dumps(actions, indent=2), encoding="utf-8",
    )
    ac.execute_files([str(ACTION_PATH)])


if __name__ == "__main__":
    main()
