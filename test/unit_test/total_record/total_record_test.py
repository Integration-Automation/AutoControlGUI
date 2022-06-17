import sys
from time import sleep

from je_auto_control import keys_table
from je_auto_control import press_key
from je_auto_control import release_key
from je_auto_control import test_record_instance
from je_auto_control import write


test_record_instance.set_record_enable(True)

print(keys_table.keys())

press_key("shift")
write("123456789")
press_key("return")
release_key("return")
release_key("shift")
press_key("return")
release_key("return")
print(write("abcdefghijklmnopqrstuvwxyz") == "abcdefghijklmnopqrstuvwxyz")
press_key("return")
release_key("return")
"""
this write will print one error -> keyboard write error can't find key : Ѓ and write remain string
"""
try:
    print (write("?123456789") == "123456789")
except Exception as error:
    print(repr(error), file=sys.stderr)
try:
    write("!#@L@#{@#PL#{!@#L{!#{|##PO}!@#O@!O#P!)KI#O_!K")
except Exception as error:
    print(repr(error), file=sys.stderr)

print(test_record_instance.test_record_list)
