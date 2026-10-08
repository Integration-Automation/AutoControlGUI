=================
Runnable Examples
=================

The ``examples/`` folder of the repository holds one short script per feature.
The six below cover the features added most recently, and each of them accepts
``--validate``:

.. code-block:: bash

   pip install -e .
   python examples/29_config_sync.py --validate

With ``--validate`` a script exercises the real API against an in-memory, temp
directory or loopback stand-in and exits ``0`` when what it observed is what
the documentation promises. It never moves the pointer, types, captures the
screen, reaches a device, or talks to anything beyond ``127.0.0.1``. CI runs
all six this way (``test_modernization_examples.py``), with every input and
process seam replaced by a tripwire.

That is evidence the calls are wired the way these pages say. It is not
evidence about hardware: nothing here has touched a Wayland compositor, an
Android device or an iPhone. Where a real run needs something, the script's
own docstring names it.

.. list-table::
   :header-rows: 1
   :widths: 30 40 30

   * - Script
     - What ``--validate`` does
     - Without the flag
   * - ``28_wayland_diagnostics.py``
     - Probes four described desktops (GNOME before and after a refused
       consent, sway with ``ydotool``, X11 on a Wayland session) and journals
       a dry run with ``InputStepLog``.
     - Probes this session. Also free of side effects.
   * - ``29_config_sync.py``
     - Two machines sync script files through a store in a temp directory:
       arrival, server restart, offline queue, a conflict and its resolution.
     - Prints the recorded status; syncs this machine only with ``--run``.
   * - ``30_mobile_devices.py``
     - Opens an Android session over an offline transport and checks which
       ``adb`` commands a setup report, a capture, gestures and typing send.
     - Prints a device's setup report; taps only with ``--tap X Y``.
   * - ``31_healing_comparison.py``
     - Scores two template-matching versions on five labelled frames drawn in
       memory (HiDPI, negative origin, absent, restyled).
     - ``--dataset FILE`` evaluates a dataset file. Offline as well.
   * - ``32_codegen_from_log.py``
     - Journals a run of variable and flow-control commands, rebuilds it as a
       candidate script and dry-runs the result.
     - ``--journal FILE`` converts a journal you recorded.
   * - ``33_mcp_progressive.py``
     - Drives an in-process MCP server: lists, searches, reads a schema and
       enables a tool. Calls no tool that touches the desktop.
     - Serves MCP over stdio in progressive mode.

Where each feature is documented
================================

.. list-table::
   :header-rows: 1
   :widths: 24 38 38

   * - Feature
     - Guide
     - Entry points
   * - Capability and authorisation states
     - :doc:`../wayland/wayland_capabilities_doc`
     - ``probe_capabilities``, ``AC_probe_capabilities``,
       ``ac_probe_capabilities``, the Diagnostics tab
   * - Recording without a global hook
     - :doc:`../record/record_doc`
     - ``InputStepLog``, ``PhysicalRecorder``, ``StopShortcutSession``
   * - Config sync
     - :doc:`../config_sync/config_sync_doc`
     - ``config_sync_run`` / ``_status`` / ``_resolve`` / ``_full_resync``,
       ``AC_config_sync_*``, ``ac_config_sync_*``, the Config Sync tab
   * - Mobile device sessions
     - :doc:`../mobile/mobile_doc`
     - ``open_device``, ``use_device``, ``run_mobile_command``,
       ``AC_android_*`` / ``AC_ios_*``, the Mobile tab
   * - Healing evaluation and template revisions
     - :doc:`../new_features/v2_features_doc`
     - ``evaluate_locators``, ``evaluate_healing_dataset``,
       ``AC_self_heal_evaluate``, ``propose_template_revision``
   * - Action journal and candidate scripts
     - :doc:`../new_features/v5_features_doc`
     - ``start_action_journal``, ``generate_candidate_from_log``,
       ``AC_journal_*``, ``je_auto_control codegen --from-log``
   * - MCP tool modes
     - :doc:`../mcp_server/mcp_server_doc`
     - ``--tool-mode``, ``JE_AUTOCONTROL_MCP_TOOL_MODE``, ``ac_tools_*``
   * - Roles and deferred ownership
     - :doc:`../operations_layer/operations_layer_doc`
     - ``JE_AUTOCONTROL_RBAC_USERS``, ``rbac_add_user``, ``AC_user_*``,
       ``je_auto_control users``
   * - Signed action files (Ed25519)
     - :doc:`../new_features/v4_features_doc`
     - ``create_signing_keypair``, ``sign_action_file``,
       ``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS``
   * - Window shell, navigation, background work
     - :doc:`../new_features/v223_features_doc`
     - the Actions and View menus, ``JE_AUTOCONTROL_GUI_SETTINGS``
   * - Every environment variable
     - :doc:`../configuration/configuration_doc`
     -

Three things the examples show that are easy to miss
====================================================

**The executor's options are on the executor object.** The module-level
``je_auto_control.execute_action(actions)`` takes the action list and nothing
else. ``dry_run``, ``raise_on_error`` and ``step_callback`` belong to
``je_auto_control.executor.execute_action``:

.. code-block:: python

   import je_auto_control as ac

   ac.executor.execute_action(actions, dry_run=True)          # resolve, call nothing
   ac.executor.execute_action(actions, raise_on_error=True)   # stop at the first failure

**A failed sync backs off.** After a send that did not reach the server, the
next ``config_sync_run`` inside the back-off window (2 s, doubling, capped at
5 minutes) does not contact the server: it reports ``offline`` again with
``error`` set to ``waiting to retry after an earlier failure``. Pass
``wait=True`` to sleep through the back-off instead — that is what a scheduled
sync wants, and a ``cancel`` event ends the wait.

**Searching a tool does not enable it.** In progressive mode
``ac_tools_search`` and ``ac_tools_schema`` only describe; the session's
``tools/list`` changes when ``ac_tools_enable`` is called, and the client is
told with ``notifications/tools/list_changed``.

The validation path of each script
==================================

These are included from the scripts themselves, so they are what CI runs.

.. literalinclude:: ../../../../../examples/28_wayland_diagnostics.py
   :language: python
   :pyobject: validate
   :caption: examples/28_wayland_diagnostics.py

.. literalinclude:: ../../../../../examples/29_config_sync.py
   :language: python
   :pyobject: _walkthrough
   :caption: examples/29_config_sync.py

.. literalinclude:: ../../../../../examples/30_mobile_devices.py
   :language: python
   :pyobject: validate
   :caption: examples/30_mobile_devices.py

.. literalinclude:: ../../../../../examples/31_healing_comparison.py
   :language: python
   :pyobject: validate
   :caption: examples/31_healing_comparison.py

.. literalinclude:: ../../../../../examples/32_codegen_from_log.py
   :language: python
   :pyobject: validate
   :caption: examples/32_codegen_from_log.py

.. literalinclude:: ../../../../../examples/33_mcp_progressive.py
   :language: python
   :pyobject: validate
   :caption: examples/33_mcp_progressive.py
