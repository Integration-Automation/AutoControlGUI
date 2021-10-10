import sys

if sys.platform not in ["darwin"]:
    raise Exception("should be only loaded on MacOS")

import time

import Quartz

from je_auto_control.osx.core.utils.osx_vk import osx_mouse_left
from je_auto_control.osx.core.utils.osx_vk import osx_mouse_middle
from je_auto_control.osx.core.utils.osx_vk import osx_mouse_right


def position():
    """
    get mouse current position
    """
    return (Quartz.NSEvent.mouseLocation().x, Quartz.NSEvent.mouseLocation().y)


def mouse_event(event, x, y, mouse_button):
    """
    :param event which event we want to use
    :param x event x
    :param y event y
    :param mouse_button which mouse button will use event
    """
    curr_event = Quartz.CGEventCreateMouseEvent(None, event, (x, y), mouse_button)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, curr_event)


def set_position(x, y):
    """
    :param x we want to set mouse x position
    :param y we want to set mouse y position
    """
    mouse_event(Quartz.kCGEventMouseMoved, x, y, 0)


def press_mouse(mouse_button, x, y):
    """
    :param x event x
    :param y event y
    :param mouse_button which mouse button press
    """
    if mouse_button is osx_mouse_left:
        mouse_event(Quartz.kCGEventLeftMouseDown, x, y, Quartz.kCGMouseButtonLeft)
    elif mouse_button is osx_mouse_middle:
        mouse_event(Quartz.kCGEventOtherMouseDown, x, y, Quartz.kCGMouseButtonCenter)
    elif mouse_button is osx_mouse_right:
        mouse_event(Quartz.kCGEventRightMouseDown, x, y, Quartz.kCGMouseButtonRight)


def release_mouse(x, y, mouse_button):
    """
    :param x event x
    :param y event y
    :param mouse_button which mouse button release
    """
    if mouse_button is osx_mouse_left:
        mouse_event(Quartz.kCGEventLeftMouseUp, x, y, Quartz.kCGMouseButtonLeft)
    elif mouse_button is osx_mouse_middle:
        mouse_event(Quartz.kCGEventOtherMouseUp, x, y, Quartz.kCGMouseButtonCenter)
    elif mouse_button is osx_mouse_right:
        mouse_event(Quartz.kCGEventRightMouseUp, x, y, Quartz.kCGMouseButtonRight)


def click_mouse(x, y, mouse_button):
    """
    :param x event x
    :param y event y
    :param mouse_button which mouse button click
    """
    if mouse_button is osx_mouse_left:
        press_mouse(x, y, mouse_button)
        time.sleep(.001)
        release_mouse(x, y, mouse_button)
    elif mouse_button is osx_mouse_middle:
        press_mouse(x, y, mouse_button)
        time.sleep(.001)
        release_mouse(x, y, mouse_button)
    elif mouse_button is osx_mouse_right:
        press_mouse(x, y, mouse_button)
        time.sleep(.001)
        release_mouse(x, y, mouse_button)


def scroll(scroll_value):
    """
    :param scroll_value scroll count
    """
    scroll_value = int(scroll_value)
    for do_scroll in range(abs(scroll_value)):
        scroll_event = Quartz.CGEventCreateScrollWheelEvent(
            None,
            0,
            1,
            1 if scroll_value >= 0 else -1
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, scroll_event)
