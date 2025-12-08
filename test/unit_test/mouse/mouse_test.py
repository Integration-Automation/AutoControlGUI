try:
    import sys
    import time

    from je_auto_control import click_mouse
    from je_auto_control import get_mouse_position
    from je_auto_control import mouse_keys_table
    from je_auto_control import press_mouse
    from je_auto_control import release_mouse
    from je_auto_control import set_mouse_position

    time.sleep(3)

    print(get_mouse_position())
    set_mouse_position(809, 388)

    print(mouse_keys_table.keys())

    press_mouse("mouse_right")
    release_mouse("mouse_right")
    press_mouse("mouse_left")
    release_mouse("mouse_left")
    click_mouse("mouse_left")
except Exception:
    sys.exit(0)
