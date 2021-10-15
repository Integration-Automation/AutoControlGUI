import sys
from je_auto_control import execute_action


test_list = None
if sys.platform in ["win32", "cygwin", "msys"]:
    test_list = [("keyboard", 65), ("keyboard", 0x41), ("keyboard", 0x41), ("keyboard", 0x41)]
elif sys.platform in ["linux", "linux2"]:
    test_list = [("keyboard", 38), ("keyboard", 38), ("keyboard", 38), ("keyboard", 38)]
elif sys.platform in ["darwin"]:
    test_list = [("keyboard", 0x00), ("keyboard", 0x00), ("keyboard", 0x00), ("keyboard", 0x00)]
execute_action(test_list)
