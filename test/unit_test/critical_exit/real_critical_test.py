import sys

from je_auto_control import AutoControlMouseException
from je_auto_control import CriticalExit
from je_auto_control import press_keyboard_key
from je_auto_control import set_mouse_position
from je_auto_control import screen_size

# print your screen width and height

print(screen_size())

# simulate you can't use your mouse because you use while true to set mouse position

try:
    from time import sleep

    sleep(3)
    while True:
        set_mouse_position(200, 400)
        set_mouse_position(400, 600)
        raise AutoControlMouseException
except Exception as error:
    print(repr(error), file=sys.stderr)
    CriticalExit().init_critical_exit()
    press_keyboard_key("f7")
    sys.exit(0)
