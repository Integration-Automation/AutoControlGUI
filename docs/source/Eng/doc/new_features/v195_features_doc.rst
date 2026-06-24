Realize Off-Screen Items in Virtualized Lists / Grids
=====================================================

Long lists, data grids and trees (WPF / WinUI / File Explorer / virtual
treeviews) only materialize the rows that are scrolled into view — a row that is
off-screen has **no** accessibility element at all. So
``list_accessibility_elements`` / ``read_control_table`` / ``select_control_item``
simply cannot see it, and ``scroll_control_into_view`` can't help because the
target element does not exist yet. This is the classic "element not found in a
long list" wall.

``realize_item`` closes that gap: it locates the item inside its container by
property (UI Automation ``ItemContainerPattern.FindItemByProperty``) and realizes
it (``VirtualizedItemPattern.Realize``) so it materializes as a real element you
can then click or read.

It is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam (the same seam the rest of the accessibility module uses) — headless-testable
on any platform by injecting a fake backend; the real UIA calls live in the
Windows backend. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import realize_item, click_accessibility_element

    # Bring a far-down row into existence, then act on it:
    row = realize_item("Order 5000", container_name="Orders")
    if row is not None:
        click_accessibility_element(name=row.name)   # now a real element

    realize_item("row-42", by="automation_id", container_name="DataGrid")

``item_name`` is matched against the item's Name (``by="name"``, default) or its
AutomationId (``by="automation_id"``). The container is located by
``container_name`` / ``container_role`` / ``app_name`` / ``automation_id`` (the
same matchers as the other native-control actions). Returns the realized
``AccessibilityElement``, or ``None`` if the container or item isn't found.

Executor commands
-----------------

``AC_realize_item`` (``item_name`` / ``by`` / ``container_name`` /
``container_role`` / ``app_name`` / ``automation_id``) returns
``{found, element}``. It is exposed as the read-only ``ac_realize_item`` MCP tool
and as a Script Builder command under **Native UI**.
