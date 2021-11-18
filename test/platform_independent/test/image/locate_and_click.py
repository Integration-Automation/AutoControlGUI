import time

from je_auto_control import locate_and_click

time.sleep(2)
"""
mouse_keycode what mouse keycode you want to click
detect_threshold 0~1 , 1 is absolute equal
draw_image, mark the find target    
"""
image_data = locate_and_click("../test_source/test_template.png", mouse_keycode="mouse_left", detect_threshold=0.9,
                              draw_image=False)
print(image_data)
