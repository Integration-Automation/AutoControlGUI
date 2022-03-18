import sys
from time import sleep

from je_auto_control import set_position
from je_auto_control import size
from je_auto_control import CriticalExit
from je_auto_control import press_key
from je_auto_control import AutoControlMouseException

"""
print your screen width and height
"""
print(size())

"""
simulate you can't use your mouse because you use while true to set mouse position
"""
CriticalExit().init_critical_exit()
try:
    while True:
        set_position(200, 400)
        set_position(400, 600)
        press_key("f7")
except Exception as error:
    print(repr(error), file=sys.stderr)
