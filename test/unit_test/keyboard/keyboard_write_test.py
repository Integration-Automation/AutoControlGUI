import sys

from je_auto_control import keyboard_keys_table
from je_auto_control import press_keyboard_key
from je_auto_control import release_keyboard_key
from je_auto_control import write

print(keyboard_keys_table.keys())

press_keyboard_key("shift")
print(write("123456789"))
print(write("abcdefghijklmnopqrstuvwxyz"))
release_keyboard_key("shift")
print(write("abcdefghijklmnopqrstuvwxyz"))

# this writes will print one error -> keyboard write error can't find key : Ѓ and write remain string

try:
    print(write("Ѓ123456789"))
except Exception as error:
    print(repr(error), file=sys.stderr)
sys.exit(0)
