==============================================
New Features (2026-06-19) — Native UI Control
==============================================

Object-level desktop automation: read and drive native controls through
the OS accessibility API instead of clicking pixels or OCR-ing text. This
is far more reliable than coordinate/image automation for native apps —
the controls are addressed by name / role / app / **AutomationId**, so
they survive layout changes.

The accessibility layer previously only *listed*, *found*, and *clicked*
elements; it now also *acts* on them via their control patterns. Ships
through the full stack (facade, ``AC_*`` executor commands, MCP tools,
Script Builder), with a Windows UIAutomation backend; backends that can't
perform an action raise a clear ``AccessibilityNotAvailableError``.

.. contents::
   :local:
   :depth: 2


Reading and setting values
==========================

::

    from je_auto_control import control_get_value, control_set_value

    # Read a textbox / combo value directly (no OCR).
    user = control_get_value(name="Username", app_name="myapp.exe")

    # Set a value in one call (no per-key typing / focus dance).
    control_set_value("alice@example.com", automation_id="emailField")

``control_get_value`` returns the control's value text (or ``None`` when
no match); ``control_set_value`` writes it via the Value pattern and
returns ``True`` on success.

Executor commands: ``AC_control_get_value``, ``AC_control_set_value``.


Invoking and toggling
====================

::

    from je_auto_control import control_invoke, control_toggle

    control_invoke(name="Sign in")          # press a button
    control_toggle(name="Remember me")      # flip a checkbox / switch

``control_invoke`` triggers a control's default action (Invoke pattern);
``control_toggle`` flips a checkbox/switch (Toggle pattern). Both return
``True`` on success.

Executor commands: ``AC_control_invoke``, ``AC_control_toggle``.


Reading tables / grids
====================

::

    from je_auto_control import read_control_table

    rows = read_control_table(name="Results", app_name="myapp.exe")
    # -> [["Sam", "30"], ["Lee", "25"], ...]

``read_control_table`` reads a grid/table/list control into rows of cell
strings via the Grid pattern — reliable desktop data scraping without OCR.

Executor command: ``AC_read_table``.


Targeting controls
=================

Every call accepts the same matchers — provide whichever uniquely
identify the control:

* ``name`` — the control's accessible name / label.
* ``role`` — the control type.
* ``app_name`` — the owning application (e.g. ``notepad.exe``).
* ``automation_id`` — the most stable identifier (Windows AutomationId),
  unaffected by layout or localization.


Platforms
=========

A Windows UIAutomation backend (via ``comtypes``) implements all four
actions. On platforms / backends without a control driver yet, the calls
raise ``AccessibilityNotAvailableError`` with a clear message rather than
silently failing. The backend is swappable, so the logic is unit-tested
with an injected fake — no real GUI required.
