import sys

from je_auto_control import keys_table
from je_auto_control import type_key
from je_auto_control import press_key
from je_auto_control import release_key
from je_auto_control import AutoControlKeyboardException

"""
check keys
"""
print(keys_table.keys())
assert (type_key("T") == "T")
assert (type_key("E") == "E")
assert (type_key("S") == "S")
assert (type_key("T") == "T")


