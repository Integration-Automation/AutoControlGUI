Rich UIA Element Properties
===========================

``list_accessibility_elements`` / ``AccessibilityElement`` carry only name / role /
bounds / app / pid / automation_id. Automation routinely needs more *before it
acts*: **is the control enabled** (don't click a disabled button), **is it
off-screen** (is it really visible?), its **item_status** (validation / error text
on a field), **help_text** (tooltip), and **accelerator_key** (drive it via a
hotkey instead of a click). ``ax_props`` exposes those high-value UIA properties.

* :func:`get_element_properties` — the full property dict,
* :func:`is_element_enabled` — the common pre-action guard.

Each function is a thin dispatch onto the injectable
``accessibility.backends.get_backend()`` seam — headless-testable on any platform
by injecting a fake backend; the real UIA property reads live in the Windows
backend. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import get_element_properties, is_element_enabled

    get_element_properties(name="Save", role="button")
    # {"enabled": False, "offscreen": False, "help_text": "Save the file",
    #  "item_status": "", "accelerator_key": "Ctrl+S", "access_key": "S",
    #  "orientation": 0}

    if is_element_enabled(name="Submit"):
        click_text("Submit")          # don't click a disabled button

The control is located by ``name`` / ``role`` / ``app_name`` / ``automation_id``
(same as the other native-control reads). ``get_element_properties`` returns the
property dict or ``None`` when the control isn't found; ``is_element_enabled``
returns the ``enabled`` flag (or ``None`` if not found).

Executor commands
-----------------

``AC_get_element_properties`` returns ``{found, properties}``. It is exposed as the
read-only ``ac_get_element_properties`` MCP tool and as a Script Builder command
under **Native UI**.
