import subprocess

from je_auto_control import screenshot

# choose screenshot screen_region
image = screenshot(screen_region=[300, 400, 500, 600])
assert (image is not None)
print(image)

subprocess.call("notepad.exe")

# screenshot and save
image = screenshot("test.png")
assert (image is not None)
print(image)

# only screenshot
image = screenshot()
assert (image is not None)
print(image)
