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
try:
    from time import sleep
    sleep(3)
    while True:
        set_position(200, 400)
        set_position(400, 600)
        raise AutoControlMouseException
except AutoControlMouseException:
    CriticalExit().init_critical_exit()
    press_key("f7")
