from je_auto_control import keyboard_keys_table
from je_auto_control import type_keyboard

# check keys
print(keyboard_keys_table.keys())
assert (type_keyboard("T") == "T")
assert (type_keyboard("E") == "E")
assert (type_keyboard("S") == "S")
assert (type_keyboard("T") == "T")
