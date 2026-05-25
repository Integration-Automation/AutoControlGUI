"""iOS device backend (WebDriverAgent / facebook-wda).

Typical usage::

    from je_auto_control.ios import tap, swipe, find_element, screenshot

    tap(180, 800)
    swipe(180, 1000, 180, 200)
    find_element(name="Sign in")
    screenshot("/tmp/phone.png")

WebDriverAgent must be running on the device — see the Facebook
WDA README for installation. ``facebook-wda`` is an optional pip
dependency that loads lazily so importing this module on a non-Mac
host does not fail.
"""
from je_auto_control.ios.client import (
    IOSDevice, IOSUnavailableError,
    default_ios_device, reset_default_ios_device,
)
from je_auto_control.ios.find import (
    ElementNotFoundError, click_element, dump_source, find_element,
)
from je_auto_control.ios.input import (
    long_press, press_key, swipe, tap, type_text,
)
from je_auto_control.ios.screen import screen_size, screenshot


__all__ = [
    "ElementNotFoundError", "IOSDevice", "IOSUnavailableError",
    "click_element", "default_ios_device", "dump_source",
    "find_element", "long_press", "press_key",
    "reset_default_ios_device", "screen_size", "screenshot", "swipe",
    "tap", "type_text",
]
