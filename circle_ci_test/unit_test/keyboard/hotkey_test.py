import sys

from je_auto_control import hotkey

if sys.platform in ["win32", "cygwin", "msys"]:
    hotkey(["lcontrol", "a"])
    hotkey(["lcontrol", "c"])
    hotkey(["lcontrol", "v"])
    hotkey(["lcontrol", "v"])

elif sys.platform in ["darwin"]:
    hotkey(["command", "a"])
    hotkey(["command", "c"])
    hotkey(["command", "v"])
    hotkey(["command", "v"])

elif sys.platform in ["linux", "linux2"]:
    hotkey(["ctrl", "a"])
    hotkey(["ctrl", "c"])
    hotkey(["ctrl", "v"])
    hotkey(["ctrl", "v"])
