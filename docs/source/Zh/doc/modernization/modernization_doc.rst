改版流程範例
========================

Run from the repository root with ``--validate``. Validation uses disposable fixtures and passive metadata; native operation requires the explicit flags described in the workflow guide.

28_wayland_diagnostics
----------------------

.. literalinclude:: ../../../../../examples/28_wayland_diagnostics.py
   :language: python

29_config_sync
--------------

.. literalinclude:: ../../../../../examples/29_config_sync.py
   :language: python

30_mobile_devices
-----------------

.. literalinclude:: ../../../../../examples/30_mobile_devices.py
   :language: python

31_healing_comparison
---------------------

.. literalinclude:: ../../../../../examples/31_healing_comparison.py
   :language: python

32_codegen_from_log
-------------------

.. literalinclude:: ../../../../../examples/32_codegen_from_log.py
   :language: python

33_mcp_progressive
------------------

.. literalinclude:: ../../../../../examples/33_mcp_progressive.py
   :language: python


Integration acceptance
----------------------

Run ``python test/verify/modernization_verify.py --output acceptance-evidence`` for controlled journal replay and SQLite restart evidence. Reports preserve actual results and reasons for skipped native conditions. Python 3.10–3.14 coverage CI spans Windows/Linux/macOS; installed extras typing, physical native acceptance and production integration retain separate evidence.

Installed extras typing inspects both PySide6 and its shiboken6 companion stubs; the base gate remains independent of optional dependency installation. Business exemptions remain empty.

On Linux without an X11 display, prefix validation with ``xvfb-run -a``. Remote viewers retain the latest early JPEG until connection-ready and discard it on disconnect; replacement sessions never inherit that image.
