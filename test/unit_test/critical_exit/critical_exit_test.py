import sys

from je_auto_control import CriticalExit
from je_auto_control import keyboard_keys_table
from je_auto_control import press_keyboard_key

try:
    # Create critical exit listener default exit key is keyboard f7
    critical_exit_thread = CriticalExit()
    # set exit key you can use any key in keys_table
    print(keyboard_keys_table.keys())
    critical_exit_thread.set_critical_key("f2")
    # Start listener
    critical_exit_thread.init_critical_exit()
    # now auto press f2 will stop this program
    while True:
        press_keyboard_key("f2")
except KeyboardInterrupt:
    sys.exit(0)
