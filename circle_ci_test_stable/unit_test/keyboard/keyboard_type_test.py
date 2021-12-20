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

try:
    type_key("dwadawddwadaw")
except AutoControlKeyboardException as error:
    print(repr(error), file=sys.stderr)
# no error system will catch it but may make some system error
# you can try to reconnect usb
type_key(-1)
type_key(18919819819165161616161651651651651231231)
press_key(1616516516516516516515)
release_key(15616516516511)

