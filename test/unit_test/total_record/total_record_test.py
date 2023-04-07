import sys

from je_auto_control import keyboard_keys_table
from je_auto_control import press_keyboard_key
from je_auto_control import release_keyboard_key
from je_auto_control import test_record_instance
from je_auto_control import write

try:
    test_record_instance.set_record_enable(True)
    print(keyboard_keys_table.keys())
    press_keyboard_key("shift")
    write("123456789")
    assert (write("abcdefghijklmnopqrstuvwxyz") == "abcdefghijklmnopqrstuvwxyz")
    release_keyboard_key("shift")
    # this writes will print one error -> keyboard write error can't find key : Ѓ and write remain string
    try:
        assert (write("?123456789") == "123456789")
    except Exception as error:
        print(repr(error), file=sys.stderr)
    try:
        write("!#@L@#{@#PL#{!@#L{!#{|##PO}!@#O@!O#P!)KI#O_!K")
    except Exception as error:
        print(repr(error), file=sys.stderr)

    print(test_record_instance.test_record_list)
except Exception as error:
    print(repr(error), file=sys.stderr)
sys.exit(0)
