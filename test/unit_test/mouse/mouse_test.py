import sys
import time

from je_auto_control import AutoControlMouseException
from je_auto_control import click_mouse
from je_auto_control import mouse_keys_table
from je_auto_control import get_mouse_position
from je_auto_control import press_mouse
from je_auto_control import release_mouse
from je_auto_control import set_mouse_position

time.sleep(1)

print(get_mouse_position())
set_mouse_position(809, 388)

print(mouse_keys_table.keys())

press_mouse("mouse_right")
release_mouse("mouse_right")
press_mouse("mouse_left")
release_mouse("mouse_left")
click_mouse("mouse_left")
try:
    set_mouse_position(6468684648, 4686468648864684684)
except AutoControlMouseException as error:
    print(repr(error), file=sys.stderr)
try:
    click_mouse("dawdawddadaawd")
except AutoControlMouseException as error:
    print(repr(error), file=sys.stderr)
try:
    press_mouse("dawdawdawdawd")
except AutoControlMouseException as error:
    print(repr(error), file=sys.stderr)
try:
    release_mouse("dwadawdadwdada")
except AutoControlMouseException as error:
    print(repr(error), file=sys.stderr)
try:
    press_mouse(16515588646)
except AutoControlMouseException as error:
    print(repr(error), file=sys.stderr)
try:
    release_mouse(1651651915)
except AutoControlMouseException as error:
    print(repr(error), file=sys.stderr)
try:
    press_mouse("mouse_left")
except AutoControlMouseException as error:
    print(repr(error), file=sys.stderr)
try:
    release_mouse("mouse_left")
except AutoControlMouseException as error:
    print(repr(error), file=sys.stderr)
