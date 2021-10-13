from time import sleep

from je_auto_control import record
from je_auto_control import stop_record
from je_auto_control import type_key

record()
type_key("t")
type_key("e")
type_key("s")
type_key("t")
sleep(1)
stop_record()
sleep(1)
