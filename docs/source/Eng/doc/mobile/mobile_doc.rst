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
