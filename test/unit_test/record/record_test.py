from time import sleep

from je_auto_control import execute_action
from je_auto_control import record
from je_auto_control import stop_record
from je_auto_control import type_key

# this program will type test two time
# one time is type key one time is test_record

record()
sleep(1)
print(type_key("t"))
print(type_key("e"))
print(type_key("s"))
print(type_key("t"))
sleep(2)
record_result = stop_record()
print(record_result)
execute_action(record_result)
sleep(5)
