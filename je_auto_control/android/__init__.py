"""Phase 9.7: Android automation backend (ADB-based).

AutoControl's main API drives the local desktop. This package adds a
parallel surface for Android devices: tap, swipe, key events, screen
capture, text input, all routed through ``adb shell``. The same
action JSON files can target an Android device by prefixing the
command names with ``AC_android_*``.

Two entry points:

  * :class:`AdbClient` — low-level wrapper around the standard
    ``adb`` executable. Talks to ``adb-server`` if one is running,
    spawns it on demand otherwise. All methods take ``serial`` so
    you can drive several devices in parallel.

  * ``AC_android_*`` action commands — registered with the executor
    so a JSON file can mix desktop and mobile steps:

        ["AC_android_tap",        {"x": 540, "y": 1100, "serial": "..."}],
        ["AC_android_swipe",      {"x1": 100, "y1": 100,
                                   "x2": 800, "y2": 100, "ms": 250}],
        ["AC_android_key",        {"key": "KEYCODE_HOME"}],
        ["AC_android_text",       {"text": "hello"}],
        ["AC_android_screenshot", {"file_path": "phone.png"}],

The ADB binary is **not** bundled — install `Android Platform Tools
<https://developer.android.com/tools/releases/platform-tools>`_ and
make sure ``adb`` is on ``PATH``. iOS support is deliberately not in
this phase; it needs a Mac + paid Apple Developer cert to sideload
WebDriverAgent, which is its own infrastructure problem.
"""
from je_auto_control.android.adb_client import (
    AdbClient, AdbError, AdbNotAvailable, AndroidDevice,
)
from je_auto_control.android.client import (
    UIAutomatorDevice, UIAutomatorUnavailableError,
    default_ui_device, reset_default_ui_device,
)
from je_auto_control.android.find import (
    ElementNotFoundError, click_element, dump_hierarchy, find_element,
)

__all__ = [
    "AdbClient", "AdbError", "AdbNotAvailable", "AndroidDevice",
    "ElementNotFoundError",
    "UIAutomatorDevice", "UIAutomatorUnavailableError",
    "click_element", "default_ui_device", "dump_hierarchy",
    "find_element", "reset_default_ui_device",
]
