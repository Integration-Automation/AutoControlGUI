from time import sleep

from je_auto_control import record
from je_auto_control import stop_record
from je_auto_control import type_key
from je_auto_control import execute_action

"""
this program will type test two time
one time is type key one time is record
"""
record()
type_key("t")
type_key("e")
type_key("s")
type_key("t")
sleep(1)
record_result = stop_record()
print(record_result)
execute_action(record_result)
