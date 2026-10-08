================================
Android and iOS devices
================================

AutoControl drives Android devices through ``adb`` (plus the optional
``uiautomator2`` daemon) and iOS devices through WebDriverAgent (the
``facebook-wda`` client). Both are optional: nothing here is imported until
it is used, so the package still imports on a host with neither.

.. warning::

   **Not verified on hardware.** Everything on this page is built and tested
   against a fake ADB host and a fake WebDriverAgent client
   (``test/unit_test/headless/_mobile_doubles.py``). Those tests prove the
   commands AutoControl sends are the ones it means to send; they do not prove
   a real emulator, phone or WebDriverAgent build accepts them. No CI job
   attaches a device. Treat the setup notes below as the intended procedure,
   not as a tested one.

Device contexts and sessions
============================

A :class:`DeviceContext` is the frozen identity of one device, and
:func:`open_device` turns it into a :class:`DeviceSession` that owns its own
transport, timeout and cancellation signal::

    from je_auto_control import DeviceContext, open_device

    left = open_device(DeviceContext("android", "emulator-5554"))
    right = open_device(DeviceContext("ios", "http://192.168.1.20:8100"))

    print(left.capabilities()["unicode_text"].state)
    left.cancel()            # stops ``left`` only
    assert right.connected
    right.close()

``device_id`` is the adb serial on Android and the WebDriverAgent URL on iOS.
Opening a session sends nothing: the adb client or WDA client is built on the
first operation, so a session can be opened on a host without ``adb``.

* ``cancel()`` stops one session. A caller waiting on the device returns at
  once with ``DeviceCancelledError`` and nothing further is sent. A call
  already on its way to the device cannot be recalled.
* A call that outlives ``timeout_s`` (default 30 s) raises
  ``DeviceTimeoutError`` **and closes the session**: the device is in a state
  nobody observed, so the next step is refused (``DeviceClosedError``) instead
  of being sent on top of it. Open a new session to continue.
* ``close()`` releases what the session built. A client handed in by the
  caller (``open_device(context, adb=...)`` / ``device=...``) is used but not
  owned. Closing an iOS session never terminates an app or deletes a remote
  WDA session.

Several devices in one process
------------------------------

``use_device(session)`` binds a session for the current thread; a mobile
command that names no ``serial`` / ``url`` then targets it. The device matrix
does this for every device it runs, so two workers cannot reach each other's
device by leaving the address out::

    from je_auto_control import run_on_devices

    run_on_devices(
        actions=[["AC_android_tap", {"x": 100, "y": 200}]],
        devices=[{"platform": "android", "serial": "emulator-5554"},
                 {"platform": "android", "serial": "emulator-5556"}],
    )

An explicit ``serial`` / ``url`` in a step still wins over the bound device.
The older process-wide helpers (``default_ui_device()``,
``default_ios_device()``, the executor's per-serial adb cache) keep working
for single-device scripts; the matrix no longer touches them.

Capabilities
============

``session.capabilities()`` returns one :class:`DeviceCapability` per feature —
``input``, ``unicode_text``, ``multi_touch``, ``screenshot``, ``ui_tree``,
``app_lifecycle``, ``alerts``, ``install``, ``files``, ``clipboard``,
``recording`` — each in one of four states:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - State
     - Meaning
   * - ``available``
     - Usable now.
   * - ``needs_permission``
     - The device refused the host (USB debugging not authorised).
   * - ``needs_dependency``
     - Something is missing; ``reason`` names it (``adb``, ``uiautomator2``,
       ``facebook-wda``, an unreachable WDA endpoint, an unattached device, a
       host-side adapter).
   * - ``unsupported``
     - The backend cannot do it; ``alternative`` says what to use instead.

Probing sends no input. On Android it runs ``adb devices`` and reads one
setting; on iOS it requests WDA's ``/status``.

Errors
======

Every error derives from ``DeviceError`` (an ``AutoControlException`` and a
``RuntimeError``), whichever backend raised it:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Error
     - Raised when
   * - ``DeviceUnavailableError``
     - ``adb`` / the SDK is missing, or the device or WDA endpoint cannot be
       reached (``AdbNotAvailable``, ``AdbDeviceMissingError``,
       ``UIAutomatorUnavailableError``, ``IOSUnavailableError``).
   * - ``DevicePermissionError``
     - The device has not authorised this host (``AdbUnauthorizedError``).
   * - ``DeviceTimeoutError``
     - A call outlived the timeout (``AdbTimeoutError``); also a
       ``TimeoutError``.
   * - ``DeviceCancelledError``
     - The session was cancelled.
   * - ``DeviceClosedError``
     - The session was closed or broken by a timeout.
   * - ``DeviceUnsupportedError``
     - The backend cannot do what was asked; carries ``reason`` and
       ``alternative``.

``AdbError`` and the other pre-existing names are still raised and still
caught by existing ``except`` clauses; they now share this base.

Text
====

``session.type_text(text)`` delivers the text or raises; it never reports
success for text the device did not receive.

**Android.** ``adb shell input text`` carries printable ASCII only. It drops
or mangles everything else, turns every ``%s`` into a space, and exits 0
either way. So:

1. Printable ASCII without a literal ``%s`` goes through ``input text``.
2. Anything else goes to the `ADBKeyBoard
   <https://github.com/senzhk/ADBKeyBoard>`_ IME when it is the device's
   selected input method (``adb shell ime set
   com.android.adbkeyboard/.AdbIME``).
3. Otherwise it goes to ``uiautomator2`` when that is installed on the host.
4. With neither, ``AdbUnsupportedError`` (a ``DeviceUnsupportedError``) is
   raised and nothing is sent.

``AC_android_text`` follows the same route. ``AdbClient.text()`` itself now
refuses text ``input text`` cannot deliver instead of sending it.

.. note::

   The ADBKeyBoard broadcast returns the same result whether or not an IME
   consumed it, so delivery is inferred from the IME being selected, not
   confirmed by the device.

**iOS.** WebDriverAgent's key endpoint carries Unicode; the text is passed
through unchanged.

Gestures
========

``session.perform(gesture)`` takes one of five frozen dataclasses, all in
device input coordinates:

.. list-table::
   :header-rows: 1
   :widths: 22 39 39

   * - Gesture
     - Android
     - iOS
   * - ``Tap(x, y)``
     - ``input tap``
     - WDA tap
   * - ``LongPress(x, y, duration_s)``
     - ``input swipe`` that does not move
     - WDA touch-and-hold
   * - ``Swipe(x1, y1, x2, y2, duration_s)``
     - ``input swipe``
     - WDA drag
   * - ``Drag(x1, y1, x2, y2, hold_s, duration_s)``
     - ``input draganddrop``; falls back to ``uiautomator2`` on a device
       whose ``input`` lacks it
     - WDA drag with ``hold_s`` as the press duration
   * - ``Pinch(x, y, scale, duration_s, span)``
     - ``uiautomator2`` two-pointer gesture; ``adb shell input`` has one
       pointer, so without it this raises ``DeviceUnsupportedError``
     - Pinch on the frontmost application. WDA pinches an element, not a
       coordinate, so ``x`` / ``y`` / ``span`` are ignored.

Frames and coordinates
======================

``session.capture()`` returns a :class:`DeviceFrame`: the screenshot, upright,
together with the size of the input coordinate space.

* On **iOS** WebDriverAgent takes *points* and returns *pixels* (three per
  point on most iPhones). ``frame.pixel_to_point(x, y)`` converts; tapping a
  screenshot pixel as if it were a point lands in the wrong place.
* On **Android** ``screencap`` and ``input tap`` share one coordinate space
  and the mapping is the identity. This is checked against ``wm size`` and the
  display rotation rather than assumed.
* A screenshot that comes back in the panel's natural orientation while the
  display is rotated is turned upright before anything is located in it. Which
  way to turn it (270 degrees for ``landscape_left``, 90 for
  ``landscape_right``) follows the platforms' documented conventions and has
  not been checked on a device. An upside-down display cannot be told from the
  image shape and is taken as already upright.

Locating
--------

A frame is searched directly — the host's desktop is never captured — and
every answer is in device points, ready for a gesture::

    from je_auto_control import Tap, self_heal_locate

    frame = session.capture()
    session.perform(Tap(*frame.locate_image("login_button.png")))

    point = frame.locate_text("Sign in")              # OCR, or None
    point = frame.locate_description("the blue button")   # VLM, or None

    outcome = self_heal_locate(template_path="login_button.png",
                               description="the login button", frame=frame)
    if outcome.found:
        session.perform(Tap(*outcome.coordinates))

``self_heal_locate(..., frame=frame)`` runs the same template-then-VLM
fallback and writes the same heal log; ``screen_region`` does not apply to a
frame. ``self_heal_click`` still clicks the desktop mouse and takes no frame.

App lifecycle and alerts
========================

::

    from je_auto_control import (
        AppState, accept_alert, launch_app, stop_app, wait_for_app,
    )

    launch_app(session, "com.example.shop")          # Android package / iOS bundle id
    wait_for_app(session, "com.example.shop", timeout_s=15)
    accept_alert(session)
    assert stop_app(session, "com.example.shop") == AppState.NOT_RUNNING

``AppState`` is ``not_installed``, ``not_running``, ``background`` or
``foreground``, and compares equal to those strings.

.. list-table::
   :header-rows: 1
   :widths: 22 39 39

   * - Call
     - Android
     - iOS
   * - ``launch_app``
     - ``monkey -p <package> -c android.intent.category.LAUNCHER 1``, or
       ``am start -n`` for a ``package/activity`` id
     - WDA app launch
   * - ``stop_app``
     - ``am force-stop``
     - WDA app terminate
   * - ``app_state``
     - ``pidof``, ``pm path`` and the resumed activity from ``dumpsys``
     - WDA app state. WDA reports an app that is not installed as not
       running, so ``not_installed`` is never returned.
   * - ``wait_for_app``
     - Polls ``app_state`` until the timeout, raising ``DeviceTimeoutError``;
       cancelling the session ends the wait.
     - Same.
   * - ``accept_alert`` / ``dismiss_alert``
     - Presses the standard dialog or permission button through
       ``uiautomator2`` (``android:id/button1`` / ``button2``, the permission
       controller's allow / deny buttons). Without ``uiautomator2`` it raises
       ``DeviceUnsupportedError``; locate the button in a frame and tap it
       instead.
     - WDA alert accept / dismiss; returns the alert text.

With no alert showing, both raise ``AlertNotPresentError``. An app id is
validated before it reaches the device shell.

A device-matrix spec may name an ``app_id``: the app is launched and in front
before the first step and stopped afterwards whether the steps passed or not
(``"keep_app": true`` leaves it running). ``DeviceResult.app_state`` records
where it ended up.

Install, files, clipboard, recording
====================================

These are the features a backend may not have. ``mobile_extension(session)``
returns a :class:`MobileExtension`; ``capability(feature)`` says whether each
of ``install``, ``files``, ``clipboard`` and ``recording`` can be used, and a
method whose feature is missing raises ``DeviceUnsupportedError`` with the
reason::

    from je_auto_control import mobile_extension

    extension = mobile_extension(session)
    if extension.capability("recording").available:
        extension.start_recording(time_limit_s=60)
        ...
        extension.stop_recording("run.mp4")

.. list-table::
   :header-rows: 1
   :widths: 18 41 41

   * - Feature
     - Android
     - iOS (WebDriverAgent)
   * - ``install``
     - ``adb install -r``
     - ``needs_dependency``: WDA has no install endpoint.
   * - ``files``
     - ``adb push`` / ``adb pull``
     - ``needs_dependency``: WDA has no file endpoint.
   * - ``clipboard``
     - Through ``uiautomator2``; ``needs_dependency`` without it, because
       ``adb`` cannot reach the clipboard on current Android.
     - Set only. Reading is allowed by WDA only while WDA itself is in front,
       and raises ``DeviceUnsupportedError`` on a ``facebook-wda`` build
       without ``get_clipboard``.
   * - ``recording``
     - ``adb shell screenrecord`` (180 s at most), stopped with ``SIGINT`` so
       the file is finalised, then pulled and removed from the device. A
       recording is device-side state: it is not stopped by closing the
       session, only by ``stop_recording``.
     - ``needs_dependency``: WDA has no recording endpoint.

Nothing from ``adb`` is used for an iOS device. To add the missing iOS
features, register an adapter around a host-side tool; it is asked first and
WebDriverAgent covers what it does not provide::

    from je_auto_control import register_mobile_extension

    register_mobile_extension("ios", lambda session: MyTideviceAdapter(session))

No such adapter ships with AutoControl.

Commands, MCP tools, Script Builder, GUI
========================================

Every mobile command is described once, in
``je_auto_control.MOBILE_COMMANDS`` (``wrapper/mobile_commands.py``). The
executor's ``AC_android_*`` / ``AC_ios_*`` commands, the ``ac_android_*`` /
``ac_ios_*`` MCP tools, the Script Builder's **Android** and **iOS**
categories and the **Mobile** tab are all generated from that table, so a
command cannot exist on one surface and be missing from another
(``test_mobile_surface_parity.py`` fails if it does).

Each command takes an optional address — ``serial`` and ``adb_path`` on
Android, ``url`` on iOS — plus ``device_timeout_s``. Without an address it
runs on the session bound by ``use_device`` (a device-matrix worker), else on
the backend's default device. Unknown parameters are rejected.

.. list-table::
   :header-rows: 1
   :widths: 24 38 38

   * - Group
     - Android
     - iOS
   * - Device
     - ``AC_android_device_info``, ``AC_android_screen_info``,
       ``AC_android_list_devices``
     - ``AC_ios_device_info``, ``AC_ios_screen_info``
   * - Input
     - ``AC_android_tap``, ``_swipe``, ``_long_press``, ``_drag``,
       ``_pinch``, ``_key``, ``_text``, ``_type_text``
     - ``AC_ios_tap``, ``_swipe``, ``_long_press``, ``_drag``, ``_pinch``,
       ``_press_key``, ``_type``
   * - Screen and locating
     - ``AC_android_screenshot``, ``_find_image``, ``_find_text``,
       ``_find_by_description``, ``_self_heal``, ``_find_element``,
       ``_click_element``, ``_dump_hierarchy``
     - ``AC_ios_screenshot``, ``_find_image``, ``_find_text``,
       ``_find_by_description``, ``_self_heal``, ``_find_element``,
       ``_click_element``, ``_dump_source``
   * - Apps and alerts
     - ``AC_android_launch_app``, ``_stop_app``, ``_app_state``,
       ``_wait_for_app``, ``_alert_accept``, ``_alert_dismiss``
     - the same six under ``AC_ios_``
   * - Extensions
     - ``AC_android_install_app``, ``_push_file``, ``_pull_file``,
       ``_get_clipboard``, ``_set_clipboard``, ``_start_recording``,
       ``_stop_recording``
     - the same seven under ``AC_ios_``; all but ``_set_clipboard`` raise
       ``DeviceUnsupportedError`` until an adapter is registered
   * - Shell
     - ``AC_android_shell``
     - none: there is no shell to run on iOS

The ``_find_*`` and ``_self_heal`` commands take ``tap`` to tap what they
find. ``AC_android_shell`` runs an arbitrary command on the device and is
deliberately not offered as an MCP tool.

From Python the same table is reachable as
``run_mobile_command(name, params)`` and ``mobile_capability_matrix()``; the
latter also lists the desktop features with no mobile counterpart (window
management, mouse buttons and wheel, keyboard shortcuts, the desktop
accessibility tree, COM, USB host passthrough, global hotkeys, desktop
capture) with the limitation and the alternative for each.

**Mobile tab.** Pick the platform, enter the serial or WebDriverAgent URL,
choose a command and edit its parameters as a JSON object. *Probe device*,
*Run command* and *Fill parameter template* are in the Actions menu. Probing
shows the capability table and the setup report and sends no input. Both
actions run on the GUI thread and block it until the device answers or the
timeout passes.

Setup
=====

.. warning::

   Untested on hardware. These are the steps the code is written for; none of
   them was carried out against a real emulator, phone or WebDriverAgent.

Android emulator or device
--------------------------

1. Install `Android platform-tools
   <https://developer.android.com/tools/releases/platform-tools>`_ and put
   ``adb`` on ``PATH`` (or pass ``adb_path``).
2. Emulator: start an AVD; it appears as ``emulator-5554``. Device: enable
   *Developer options* and *USB debugging*, connect it, and accept the
   authorisation prompt. Over Wi-Fi: ``adb connect <ip>:5555``.
3. ``adb devices`` must show the serial in state ``device``. ``unauthorized``
   surfaces here as ``needs_permission`` / ``DevicePermissionError``.
4. Optional, for the widget tree, pinch, dialogs, clipboard and Unicode text:
   ``pip install uiautomator2``.
5. Optional, for Unicode text without ``uiautomator2``: install ADBKeyBoard
   and select it with ``adb shell ime set com.android.adbkeyboard/.AdbIME``.
6. Check: ``AC_android_device_info`` (or the Mobile tab's *Probe device*)
   reports the adb build, the Android release and each capability.

iOS device or simulator, local or remote WebDriverAgent
-------------------------------------------------------

Building and signing WebDriverAgent needs a Mac with Xcode; for a physical
device it also needs an Apple developer signing identity. AutoControl does
not build or install it.

1. On the Mac, build and run WebDriverAgent on the device or simulator
   (``xcodebuild ... test`` on the ``WebDriverAgentRunner`` scheme) and make
   port 8100 reachable — ``iproxy 8100 8100`` for a USB device.
2. On the host that runs AutoControl (any OS): ``pip install facebook-wda``.
3. Local: the URL is ``http://localhost:8100``. Remote: use the Mac's or the
   device's address, for example ``http://192.168.1.20:8100``. WebDriverAgent
   has no authentication, so keep it on a trusted network or behind a tunnel.
4. Check: ``AC_ios_device_info`` with ``url`` reports the WebDriverAgent
   build and the iOS version from ``/status``; an endpoint that does not
   answer is reported as ``needs_dependency`` with the connection error.

Driving a remote WebDriverAgent from Windows or Linux is the supported way to
use iOS from those hosts. That is not a claim that Xcode builds or signing
were verified on them.
