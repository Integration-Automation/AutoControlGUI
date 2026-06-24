MSAA Bridge for Legacy Controls (LegacyIAccessible)
===================================================

Many legacy Win32 / MFC / Delphi controls expose **nothing useful** via the modern
UI Automation patterns — ``control_get_value`` / ``control_invoke`` /
``control_toggle`` all return None or do nothing — yet they are fully described
through the MSAA ``IAccessible`` bridge: a Name, Value, Description, Role, State
and a **DefaultAction**. ``legacy_accessible`` is the last-resort fallback that
still reads that info and fires the default action, making the long tail of old
apps automatable.

* :func:`legacy_info` — the MSAA fields ``{name, value, description,
  default_action, role, state}``,
* :func:`legacy_default_action` — fire the control's default action.

Each is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam — headless-testable via a fake backend; the real ``LegacyIAccessiblePattern``
calls live in the Windows backend. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (legacy_info, legacy_default_action,
                                 control_invoke)

    # Modern patterns came up empty? Fall back to MSAA:
    if not control_invoke(name="Apply"):
        info = legacy_info(name="Apply")          # {"default_action": "Press", ...}
        legacy_default_action(name="Apply")        # fires the MSAA default action

The control is located by ``name`` / ``role`` / ``app_name`` / ``automation_id``
(same as the other native-control actions). ``legacy_info`` returns the MSAA info
dict (``role`` / ``state`` are the raw MSAA numbers) or ``None`` if the control or
pattern isn't found; ``legacy_default_action`` returns ``bool``.

Executor commands
-----------------

``AC_legacy_info`` (``{found, info}``) and ``AC_legacy_default_action``. They are
exposed as the matching ``ac_*`` MCP tools (info read-only, the action
destructive) and as Script Builder commands under **Native UI**.
