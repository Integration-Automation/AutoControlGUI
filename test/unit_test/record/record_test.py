from time import sleep

from je_auto_control import execute_action
from je_auto_control import record
from je_auto_control import stop_record
from je_auto_control import type_keyboard

# this program will type test two time
# one time is type key one time is test_record

record()
sleep(1)
print(type_keyboard("t"))
print(type_keyboard("e"))
print(type_keyboard("s"))
print(type_keyboard("t"))
sleep(2)
record_result = stop_record()
print(record_result)
execute_action(record_result)
sleep(5)
