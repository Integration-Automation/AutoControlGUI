import sys

from je_auto_control import keys_table
from je_auto_control import press_key
from je_auto_control import release_key
from je_auto_control import write

print(keys_table.keys())

press_key("shift")
write("123456789")
assert (write("abcdefghijklmnopqrstuvwxyz") == "abcdefghijklmnopqrstuvwxyz")
release_key("shift")
assert (write("abcdefghijklmnopqrstuvwxyz") == "abcdefghijklmnopqrstuvwxyz")

"""
this write will print one error -> keyboard write error can't find key : Ѓ and write remain string
"""
try:
    assert (write("Ѓ123456789") == "123456789")
except Exception as error:
    print(repr(error), file=sys.stderr)
try:
    write("!#@L@#{@#PL#{!@#L{!#{|##PO}!@#O@!O#P!)KI#O_!K")
except Exception as error:
    print(repr(error), file=sys.stderr)

