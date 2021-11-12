import sys

from je_auto_control import keys_table
from je_auto_control import press_key
from je_auto_control import release_key
from je_auto_control import write

print(keys_table.keys())

press_key("shift")
write("123456789")
press_key("return")
release_key("return")
write("abcdefghijklmnopqrstuvwxyz")
release_key("shift")
press_key("return")
release_key("return")
write("abcdefghijklmnopqrstuvwxyz")
press_key("return")
release_key("return")
"""
this write will print one error -> keyboard write error can't find key : Ѓ and write remain string
"""
write("123456789")
