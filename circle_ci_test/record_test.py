import sys
from time import sleep

from je_auto_control import record
from je_auto_control import stop_record
from je_auto_control import close_record
from je_auto_control import type_key
from je_auto_control import press_key
from je_auto_control import AutoControlException
from je_auto_control import CriticalExit

record()
type_key("t")
type_key("e")
type_key("s")
type_key("t")
sleep(1)
stop_record()
sleep(1)
