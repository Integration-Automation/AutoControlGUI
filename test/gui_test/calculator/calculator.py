from time import sleep

from je_auto_control import locate_and_click

# 開啟windows 計算機
# 並累加1至9
# open windows calc.exe
# and calculate 1 + 2 .... + 9

import subprocess  # noqa: E402  # reason: imported after instructional comments
subprocess.Popen(["calc.exe"])  # nosec B603 B607  # reason: hard-coded calc launcher used by GUI test

sleep(3)

_PLUS_IMG = "../../test_source/plus.png"
_EQUAL_IMG = "../../test_source/equal.png"
_DIGIT_IMG = "../../test_source/{n}.png"


def _click_image(image_path: str) -> None:
    locate_and_click(
        image_path,
        mouse_keycode="mouse_left",
        detect_threshold=0.9,
        draw_image=False,
    )


_click_image(_DIGIT_IMG.format(n=1))
for digit in range(2, 10):
    _click_image(_PLUS_IMG)
    _click_image(_DIGIT_IMG.format(n=digit))
_click_image(_EQUAL_IMG)
