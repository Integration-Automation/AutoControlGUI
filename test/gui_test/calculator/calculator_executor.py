from je_auto_control import executor

# 開啟windows 計算機
# 並累加1至9
# open windows calc.exe
# and calculate 1 + 2 .... + 9

_PLUS_IMG = "./test_source/plus.png"
_EQUAL_IMG = "./test_source/equal.png"
_DIGIT_IMG_FMT = "./test_source/{n}.png"


def _click_image_step(image_path: str) -> list:
    return [
        "AC_locate_and_click",
        {
            "cv2_utils": image_path,
            "mouse_keycode": "mouse_left",
            "detect_threshold": 0.9,
        },
    ]


test_list = [
    ["AC_add_package_to_executor", {"package": "subprocess"}],
    ["subprocess_Popen", {"args": "calc"}],
    ["AC_add_package_to_executor", {"package": "time"}],
    ["time_sleep", [3]],
    _click_image_step(_DIGIT_IMG_FMT.format(n=1)),
]
for digit in range(2, 10):
    test_list.append(_click_image_step(_PLUS_IMG))
    test_list.append(_click_image_step(_DIGIT_IMG_FMT.format(n=digit)))
test_list.append(_click_image_step(_EQUAL_IMG))

executor.execute_action(test_list)
