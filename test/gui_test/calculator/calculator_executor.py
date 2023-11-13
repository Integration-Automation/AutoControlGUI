import subprocess
from time import sleep

from je_auto_control import locate_and_click, executor

# 開啟windows 計算機
# 並累加1至9
# open windows calc.exe
# and calculate 1 + 2 .... + 9

test_list = [
    ["AC_add_package_to_executor", {"package": "subprocess"}],
    ["subprocess_Popen", {"args": "calc"}],
    ["AC_add_package_to_executor", {"package": "time"}],
    ["time_sleep", [3]],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/1.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/plus.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/2.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/equal.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/plus.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/3.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/equal.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/plus.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/4.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/equal.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/plus.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/5.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/equal.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/plus.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/6.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/equal.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/plus.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/7.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/equal.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/plus.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/8.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/equal.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/plus.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/9.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}],
    ["AC_locate_and_click",
     {"cv2_utils": "./test_source/equal.png", "mouse_keycode": "mouse_left", "detect_threshold": 0.9}]
]

executor.execute_action(test_list)

