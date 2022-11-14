import time

from je_auto_control import locate_all_image
from je_auto_control import screenshot

time.sleep(2)

# detect_threshold 0~1 , 1 is absolute equal
# draw_image, mark the find target

image_data = locate_all_image(screenshot(), detect_threshold=0.9, draw_image=False)
print(image_data)
