import subprocess  # nosec B404  # reason: launches notepad for the screenshot RPA test
import time

from je_auto_control import screenshot

subprocess.Popen(  # nosec B603 B607  # reason: hard-coded notepad launcher, argv list
    ["notepad.exe"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

time.sleep(10)

# screenshot and save
image = screenshot("test.png")
assert image is not None  # noqa: S101  # reason: pytest-style assertion in test script
print(image)