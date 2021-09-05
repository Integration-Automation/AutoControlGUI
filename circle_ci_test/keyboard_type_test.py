import time

from je_auto_control import type_key
from je_auto_control import keys_table

"""
check keys
"""
print(keys_table.keys())

"""
Linux in every type and press then release need stop 0.01 time in my computer,i'm not sure it's right?

example:
    type("T")
    time.sleep(0.01)
    type("E")
    time.sleep(0.01)
    type("S")
    time.sleep(0.01)
    type("T")
    time.sleep(0.01)

or:
    press_key("T")
    release_key("T")
    time.sleep(0.01)
"""

type_key("T")
type_key("E")
type_key("S")
type_key("T")
