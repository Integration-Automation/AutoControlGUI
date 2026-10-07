Owned mobile contexts
=====================

The Beta ``je_auto_control.api.mobile`` namespace exports ``DeviceContext``,
``DeviceSession``, ``DeviceSessionError``, ``open_device`` and
``probe_device_contexts``. The historical facade mirrors these names.

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
in Progress.md; Unicode, gestures and app lifecycle are subsequent E tasks.
