import sys

from je_auto_control import generate_html_report
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
    # SystemExit is not an Exception, so a mismatch escapes the enclosing
    # try block instead of being swallowed by its handler.
    if write("abcdefghijklmnopqrstuvwxyz") != "abcdefghijklmnopqrstuvwxyz":
        sys.exit("shift + write did not round-trip the alphabet")
    release_keyboard_key("shift")
    # this write will print one error -> keyboard write error can't find key : Ѓ and write remain string
    try:
        written = write("?123456789")
    except Exception as error:
        print(repr(error), file=sys.stderr)
    else:
        if written != "123456789":
            print(f"Unexpected write result: {written!r}", file=sys.stderr)
    try:
        write("!#@L@#{@#PL#{!@#L{!#{|##PO}!@#O@!O#P!)KI#O_!K")
    except Exception as error:
        print(repr(error), file=sys.stderr)

    print(test_record_instance.test_record_list)
    # html name is test.html and this html will recode all test detail
    # if test_record.init_total_record = True
    generate_html_report("test")
    sys.exit(0)
except Exception as error:
    print(repr(error), file=sys.stderr)
