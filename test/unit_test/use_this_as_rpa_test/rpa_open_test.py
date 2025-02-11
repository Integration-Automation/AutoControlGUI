import subprocess
import time

from je_auto_control import screenshot

subprocess.Popen("notepad.exe", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)

time.sleep(10)

# screenshot and save
image = screenshot("test.png")
assert (image is not None)
print(image)