Owned mobile contexts
=====================

The Beta ``je_auto_control.api.mobile`` namespace exports ``DeviceContext``,
``DeviceSession``, ``DeviceSessionError``, ``DeviceFrame``, ``Gesture``, ``open_device``,
``probe_device_contexts``, ``mobile_capture``, ``mobile_gesture`` and ``mobile_type_text``. The historical facade mirrors these names.

Explicit ownership
------------------

.. code-block:: python

   from je_auto_control.api.mobile import DeviceContext, open_device
   from je_auto_control.ios.input import tap

   context = DeviceContext('ios', 'phone-a', target='http://127.0.0.1:8100', timeout_s=5)
   with open_device(context) as session:
       with session.bind():
           tap(120, 200)  # Explicit device input; WDA must be configured first.

For Android, ``DeviceContext('android', 'emulator-5554')`` defaults its target
to that serial; ``adb_path`` optionally selects Platform Tools. iOS requires
an explicit HTTP/HTTPS/usbmux WDA URL, without URL credentials, query or fragment.
``device_id`` is a report label; ``target`` selects the actual serial/endpoint.
The identity/config is frozen and ``timeout_s`` must be finite, positive and
at most 300 seconds.

Creation is lazy. ``connected`` means that the logical owner is open, without
claiming device reachability. ``bind()`` selects an execution-local owner and
resets it on exit, including nested bindings and failures. Outside a binding,
existing helpers retain their compatible process defaults. Within a binding,
closed owners, foreign explicit clients and mismatched serial/URL overrides
fail with ``DeviceSessionError`` instead of choosing another device.

``cancel()`` and repeated ``close()`` revoke this owner. Pending requests may
finish on the device, but their late result is rejected. A waiting SDK
constructor does not block cancellation; its eventual owned Android helper is
reclaimed. Only a helper started by this uiautomator2 client is stopped, with
its SDK exit callback removed. Global ADB servers and existing device services
remain separate resources. Closing the root WDA client does not delete a
borrowed server-side app session.

Per-owner ADB subprocess, uiautomator2 RPC/shell/device-wait and WDA HTTP request
timeouts do not mutate SDK globals. SDK bootstrap and native retry internals
are not a verified total-operation deadline; real-device recovery remains an
acceptance case. Optional SDK failures retain a framework exception boundary.
References: `uiautomator2 core <https://github.com/openatx/uiautomator2/blob/master/uiautomator2/core.py>`_
and `facebook-wda client <https://github.com/openatx/facebook-wda/blob/master/wda/__init__.py>`_.

Matrix and passive metadata
---------------------------

``run_on_devices`` and ``AC_run_device_matrix`` bind one fresh owner per worker.
Implicit mobile commands target that worker's serial/URL. Device specs support
``platform``, ``serial``/``url`` (or ``target``), ``device_id``, ``timeout_s`` and
``adb_path``. Duplicate configured targets are rejected before input; endpoint
aliases pointing to the same physical device cannot be inferred automatically.
Each worker closes its owner on success or failure and returns its own result.

.. code-block:: json

   ["AC_probe_mobile_devices", {"devices": [
       {"platform": "android", "serial": "emulator-5554"},
       {"platform": "ios", "url": "http://127.0.0.1:8100"}
   ]}]

The Python probe and MCP ``ac_probe_mobile_devices`` return JSON dependency
evidence without SDK loading, device scanning, network connection or input.
Discovered dependencies report ``needs_permission`` with an explicit
connectivity/authorization-unverified reason; missing ones report
``needs_dependency``. These are passive observations. Remote probing requires
host administration; read-only tool annotations do not grant authorization.

Device Matrix exposes Inspect mobile dependencies and Run matrix in the
Actions menu. The probe displays JSON metadata; execution uses a background
worker so the editors and event loop remain responsive. Script Builder uses
the same JSON command. ``examples/mobile_contexts.py`` demonstrates a passive,
hardware-free matrix. Native Android/emulator and remote-WDA acceptance remains
in Progress.md; the dedicated mobile panel follows in E4.

Device input and immutable frames
---------------------------------

``session.type_text('測試 café 🙂')`` uses uiautomator2's Unicode IME/clipboard
route or WDA Unicode keys. Missing SDKs fail with dependency guidance; there is
no fallback to ``adb input text``. That legacy ASCII API now rejects non-ASCII
before native input. SDK input can configure its IME/clipboard; real-device
restoration and focused-field round-trip remain acceptance cases.

``Gesture`` validates kind, points and duration. Tap/long_press take one native
point, drag/swipe two, and pinch four (start1, start2, end1, end2). Duration must
fit the session request timeout. Android uses SDK click/long_click/drag/swipe
and two-pointer RPC. WDA uses native touch plus the W3C ``/actions`` endpoint
for simultaneous pinch; unsupported endpoints fail with typed errors. WDA's
swipe duration is the starting hold time, whereas Android uses motion time.

``session.capture()`` returns a ``DeviceFrame`` with immutable PNG, context,
``pixel_size``, ``point_size`` and observed clockwise orientation (0/90/180/270).
Android input units are native pixels; iOS units are UIKit points. Historical
iOS touch, viewport and tree helpers keep their numeric behavior; documentation
now names the point units accurately. Capture reads geometry around one native
screenshot and rejects changing/zero/unknown/mismatched geometry. WDA's raw
viewport read avoids its SDK fallback that can dismiss alerts or open Settings.

.. code-block:: python

   from je_auto_control.api.mobile import DeviceContext, Gesture, open_device

   context = DeviceContext('ios', 'phone-a', target='http://127.0.0.1:8100')
   with open_device(context) as session:
       frame = session.capture()
       point = frame.pixel_to_point((200, 100))
       session.perform(Gesture('tap', (point,), frame=frame))

``pixel_to_point`` uses the snapshot viewport and undoes extra display rotation.
``frame.rotated(90)`` creates a clockwise rotated view while preserving native
mapping. Attaching ``frame`` to a Gesture checks its owner and current geometry
before input, rejecting stale orientation rather than tapping old coordinates.
The device can still rotate after the final metadata read; native race/recovery
acceptance remains separate. ``examples/mobile_frame_mapping.py`` demonstrates
Retina/display-rotation mapping without device connection or input.

``frame.ocr(backend=engine)`` consumes these bytes and returns image-local OCR
matches. ``frame.locate(TemplateFrameStrategy(...))`` and ``VLMFrameStrategy``
return predictions in frame pixels, then ``pixel_to_point`` maps for native touch.
Within ``session.bind()``, ``self_heal_locate`` and ``self_heal_click`` share one
device frame between template and VLM, retain its hash in healing evidence,
and never invoke desktop capture/input. Self-heal click attaches the frame and
rechecks geometry before touch. Full-frame mobile search rejects desktop
``screen_region``; touch supports ``mouse_left`` only.

JSON action/MCP/Builder entry points
------------------------------------

``mobile_capture(file_path, device=None)``, ``mobile_gesture(gesture, device=None)``
and ``mobile_type_text(text, device=None)`` are mirrored by ``AC_mobile_*`` and
MCP ``ac_mobile_*``. ``device`` is a matrix-style object; omitting it requires an
active matrix owner. Foreign device overrides are rejected. Capture writes a
root-checked PNG and returns geometry. Text responses omit text; action/journal
arguments mask both named and positional text, preserving secret references in
journal input. Remote access requires host administration for all three services.

.. code-block:: json

   ["AC_run_device_matrix", {"devices": [
     {"platform": "android", "serial": "emulator-5554"}
   ], "actions": [
     ["AC_mobile_type_text", {"text": "測試 café 🙂"}],
     ["AC_mobile_gesture", {"gesture": {"kind": "long_press", "points": [[120, 200]], "duration_s": 1}}],
     ["AC_mobile_capture", {"file_path": "phone.png"}]
   ]}]

Use Device Matrix's Actions → Run matrix and Script Builder's Mobile category.
These controlled SDK contracts do not establish native emulator/WDA support.
References: `uiautomator2 input <https://github.com/openatx/uiautomator2/blob/master/uiautomator2/__init__.py>`_,
`two-pointer RPC <https://github.com/openatx/uiautomator2/blob/master/uiautomator2/_selector.py>`_,
`WDA SDK <https://github.com/openatx/facebook-wda/blob/master/wda/__init__.py>`_
and `WDA W3C actions <https://github.com/appium/WebDriverAgent/blob/master/WebDriverAgentLib/Commands/FBTouchActionCommands.m>`_.

Observed apps and optional extensions
-------------------------------------

The Beta API/facade additionally exports ``AppState``, ``app_state``, ``launch_app``,
``wait_for_app``, ``stop_app``, ``handle_mobile_alert``, ``MobileExtension``,
``MobileExtensionSpec``, ``run_mobile_extension``, ``mobile_app``, ``mobile_alert``
and ``mobile_extension_action``.

.. code-block:: python

   from je_auto_control.api.mobile import launch_app, stop_app, wait_for_app

   with open_device(context) as session:
       observed = launch_app(session, 'com.example.demo')
       observed = wait_for_app(session, 'com.example.demo', timeout_s=5)
       observed = stop_app(session, 'com.example.demo')

Android uses owned ADB launch/pidof/force-stop; process presence is running state.
iOS creates a new WDA session and freezes its ID, bypassing SDK global locks,
automatic retries and auto-unlock. XCTest 0/1/2–4 maps to
not_installed/not_running/running. Connection failures mean unknown state, never
not_running. Polling is cancellable with finite deadlines; first WDA construction
uses the caller's remaining request budget. A lost input reply is not replayed.

Deleting a WDA app session can terminate its app. Only confirmed owned IDs are
deleted; borrowed root sessions are preserved. Failed cleanup, including late
construction, remains retryable by repeated ``session.close()``. Android close
leaves apps running; use ``stop_app`` explicitly. iOS alerts accept/dismiss via
``handle_mobile_alert``; Android has no universal alert route, so use a specific
UI-tree selector. Native authorization/recovery remains H3 acceptance.

``session.configure_extension(MobileExtensionSpec(name, version, capabilities,
factory))`` installs passive metadata and a lazy factory(context, guard) before
first use. Factories must create one owner-bound adapter, honor guard before/after
I/O, use context.timeout_s and clean their owned resources on close. Shared native
clients are forbidden. Probes never execute factories. Missing declared operations
are unsupported; absent optional adapters report needs_dependency and recovery.

``MobileExtension`` defines install(file_path), files(action, local_path,
remote_path), clipboard(text=None), recording(file_path, duration_s), close().
Android includes ADB APK install, push/pull and SDK Unicode clipboard; iOS equivalents
and recording on either platform require an owned configured adapter. ADB is never
used as an iOS fallback. Local paths are root-checked; remote file paths accept
absolute ASCII paths without shell metacharacters or parent traversal.

.. code-block:: json

   [
     ["AC_mobile_app", {"action": "launch", "app_id": "com.example.demo"}],
     ["AC_mobile_extension", {"operation": "clipboard", "options": {"text": "測試 café 🙂"}}],
     ["AC_mobile_app", {"action": "stop", "app_id": "com.example.demo"}]
   ]

These commands use an active matrix owner, or pass an explicit device object.
``AC_mobile_alert`` takes action accept/dismiss. MCP ac_mobile_app/alert/extension,
Builder and Device Matrix Actions share the same services. Remote calls require
MANAGE_HOSTS; extension options/results are masked in automatic journals.
``examples/mobile_app_lifecycle.py`` is passive until --run explicitly opts into
native launch/stop. Controlled adapter tests establish dispatch/lifetime; emulator,
signing, real-WDA and physical recording acceptance remain H3.

WDA app operations require a dedicated idle endpoint. A bounded status preflight rejects existing or missing ownership metadata before creation; a local lease protects pending/active owners for the exact URL. WDA creation replaces its active session, so external clients and aliases must be excluded operationally. Unknown creation replies remain unknown native state and require inspection before explicit retry.
Mobile workspace and setup
--------------------------

The Mobile devices tab retains one explicit owner. Configure platform, serial/WDA
URL and timeout; Actions opens/closes the owner, inspects passive dependencies,
explicitly diagnoses authorization, runs the selected operation or validates an
entire flat mobile-only action list. Close revokes input immediately and performs
cleanup off Qt; failed cleanup is retained for retry and late results are dropped.
The 13-operation catalog supplies Android/iOS aliases and MCP/Builder enums.
``mobile_surface_matrix()`` inventories every executor command with scope/recovery.

Install optional ``uiautomator2==3.7.0`` or ``facebook-wda==1.5.4``. Android requires
SDK platform-tools, USB debugging and RSA authorization. iOS requires a signed
WebDriverAgentRunner on an Apple host/device, Developer Mode and an exclusive idle
WDA endpoint. HTTP ready status is not input permission or exclusive ownership.
The repository ``docs/MOBILE_SETUP.md`` documents signing, recovery and Docker/KVM
setup. ``docker/mobile-compose.yml`` pins Android 14/API 34; a Linux host needs
working KVM. The manual Mobile native smoke workflow preserves actual JSON/PNG/logs.
Configuration/controlled tests cannot replace successful native artifacts.

Default/``--validate`` execution below is passive. ``--connect`` diagnoses the
selected device; ``--exercise --app-id ...`` additionally launches, captures and
stops a disposable app. Unicode focus/rotation/restoration remain separate cases.

.. literalinclude:: ../../../../../examples/mobile_device_smoke.py
   :language: python
