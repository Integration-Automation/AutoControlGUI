"""Regression tests for the Android / iOS defects of the 2026-09-23 audit.

``adb shell`` hands its command line to the device shell, which parses it
again: typed text inside double quotes still expanded ``$(...)`` and could
close the quote, and a key name was pasted in unchecked. The uiautomator2,
adbutils and facebook-wda errors derive from ``Exception`` alone and escaped
``raise_on_error=False``. No device, adb server or WebDriverAgent is touched.
"""
import shlex
import sys
import types

import pytest

from je_auto_control.android import adb_client
from je_auto_control.android.client import UIAutomatorDevice
from je_auto_control.ios.client import IOSDevice


@pytest.fixture
def adb(monkeypatch):
    commands = []
    client = adb_client.AdbClient.__new__(adb_client.AdbClient)
    monkeypatch.setattr(client, "shell", lambda command, serial=None, timeout=None: commands.append(command))
    return client, commands


@pytest.mark.parametrize("text", [
    'a$(echo INJECTED)b";echo QUOTE_BREAKOUT;"',
    "`reboot`", "$HOME", "it's a 'quote'", "semi; colon && more",
])
def test_typed_text_reaches_the_device_shell_as_one_literal_word(adb, text):
    client, commands = adb
    client.text(text)
    # POSIX word splitting is what the device shell applies to the line.
    assert shlex.split(commands[0]) == ["input", "text", text.replace(" ", "%s")]


@pytest.mark.parametrize("key", ["HOME; echo INJECTED", "BACK && reboot", "$(id)", "a b"])
def test_a_key_that_is_not_a_key_name_is_refused(adb, key):
    client, commands = adb
    with pytest.raises(adb_client.AdbError, match="invalid key name"):
        client.key_event(key)
    assert commands == []


@pytest.mark.parametrize("key, sent", [("KEYCODE_HOME", "HOME"), ("BACK", "BACK"), ("4", "4")])
def test_real_key_names_still_work(adb, key, sent):
    client, commands = adb
    client.key_event(key)
    assert commands == [f"input keyevent {sent}"]


def _fake_module(monkeypatch, dotted, **attrs):
    module = types.ModuleType(dotted)
    for name, value in attrs.items():
        setattr(module, name, value)
    monkeypatch.setitem(sys.modules, dotted, module)
    return module


def test_an_adbutils_error_becomes_the_android_error(monkeypatch):
    from je_auto_control.android import find

    class AdbError(Exception):
        pass

    _fake_module(monkeypatch, "adbutils", AdbError=AdbError)

    def dump_hierarchy():
        raise AdbError("more than one device/emulator")

    device = UIAutomatorDevice(handle=types.SimpleNamespace(dump_hierarchy=dump_hierarchy))
    # By name: test_android_uiautomator reloads the client module, which
    # replaces the class object this file imported.
    with pytest.raises(Exception, match="more than one device") as raised:
        find.dump_hierarchy(device=device)
    assert type(raised.value).__name__ == "UIAutomatorUnavailableError"


def test_a_wda_error_becomes_the_ios_error(monkeypatch):
    from je_auto_control.ios import input as ios_input

    class WDAError(Exception):
        pass

    exceptions = _fake_module(monkeypatch, "wda.exceptions", WDAError=WDAError)
    _fake_module(monkeypatch, "wda", exceptions=exceptions)

    def tap(_x, _y):
        raise WDAError("invalid session id")

    # By name, like the Android test: test_ios_xcuitest reloads the client.
    with pytest.raises(Exception, match="invalid session id") as raised:
        ios_input.tap(1, 2, device=IOSDevice(handle=types.SimpleNamespace(tap=tap)))
    assert type(raised.value).__name__ == "IOSUnavailableError"
