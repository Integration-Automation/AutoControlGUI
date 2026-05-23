"""Interpolate ``${name}`` placeholders into a JSON action list.

Same execute pipeline as a regular file but the action list is loaded
from disk, run through the interpolator with a variables dict, and
forwarded to the executor.

Useful for parameterising a recorded script — e.g. swapping the target
URL, user name, or output path between runs without editing the file.
"""
import je_auto_control as ac


def main() -> None:
    actions = [
        ["AC_set_mouse_position", {"x": "${target_x}", "y": "${target_y}"}],
        ["AC_click_mouse", {"mouse_keycode": "mouse_left"}],
        ["AC_type_keyboard", {"keys_string": "${greeting}"}],
        ["AC_screenshot", {"file_path": "${output_path}"}],
    ]

    # The executor walks the list and substitutes every ``${name}``
    # against this dict; missing placeholders raise.
    variables = {
        "target_x": 200, "target_y": 200,
        "greeting": "Hello from AutoControl",
        "output_path": "after_typing.png",
    }
    ac.execute_action_with_vars(actions, variables)

    # ``interpolate_actions`` exposes the same logic if you want to
    # inspect the resolved list before executing.
    resolved = ac.interpolate_actions(actions, variables)
    print("resolved first action:", resolved[0])


if __name__ == "__main__":
    main()
