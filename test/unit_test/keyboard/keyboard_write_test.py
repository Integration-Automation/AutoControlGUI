import sys

from je_auto_control import keys_table
from je_auto_control import press_key
from je_auto_control import release_key
from je_auto_control import type_key
from je_auto_control import write

print(keys_table.keys())

press_key("shift")
write("123456789")
write("abcdefghijklmnopqrstuvwxyz")
release_key("shift")
write("abcdefghijklmnopqrstuvwxyz")

"""
this write will print one error -> keyboard write error can't find key : Ѓ and write remain string
"""
try:
    write("Ѓ123456789")
except Exception as error:
    print(repr(error), file=sys.stderr)
try:
    write("!#@L@#{@#PL#{!@#L{!#{|##PO}!@#O@!O#P!)KI#O_!K")
except Exception as error:
    print(repr(error), file=sys.stderr)
if sys.platform in ["win32", "cygwin"]:
    for i in range(61):
        type_key("back")
else:
    for i in range(61):
        type_key("backspace")
type_key("return")
