import os
import subprocess
from time import sleep

from je_auto_control import locate_and_click

subprocess.Popen("calc", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
sleep(3)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/1.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/plus.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)

locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/5.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)

locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/equal.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/plus.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/2.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/plus.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/3.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/plus.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/4.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/plus.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/6.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/plus.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/7.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/plus.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/8.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/plus.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/9.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
locate_and_click(
    os.getcwd() + "/circle_ci_test_dev/test_source/equal.png",
    mouse_keycode="mouse_left",
    detect_threshold=0.9,
    draw_image=False
)
