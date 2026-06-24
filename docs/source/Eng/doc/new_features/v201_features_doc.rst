Container Selection + View Switching (Selection / MultipleView)
===============================================================

``select_control_item`` (SelectionItemPattern) selects *one* item; the
container-level ``SelectionPattern`` answers the natural follow-up — **what is
currently selected** in a listbox / grid / tab, and **may it select multiple?** —
the assertion target after selecting. ``MultipleViewPattern`` switches a control
between its views (Explorer's list / details / tile / thumbnail), a common
precondition that otherwise needs fragile menu clicking.

* :func:`get_selection` — ``{items, can_select_multiple, is_required}``,
* :func:`list_views` — ``{current, views: [...]}``,
* :func:`set_view` — switch to a named view.

Each is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam — headless-testable via a fake backend; the real UIA calls live in the
Windows backend. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import get_selection, list_views, set_view

    get_selection(name="File List")
    # {"items": ["report.pdf", "notes.txt"], "can_select_multiple": True,
    #  "is_required": False}

    list_views(name="File List")
    # {"current": "Details", "views": ["List", "Details", "Tiles"]}
    set_view("Tiles", name="File List")        # switch the view

The control is located by ``name`` / ``role`` / ``app_name`` / ``automation_id``
(same as the other native-control actions). ``get_selection`` / ``list_views``
return their dict (or ``None`` if the control or pattern isn't found);
``set_view`` returns ``bool`` (False when the named view isn't supported).

Executor commands
-----------------

``AC_get_selection`` (``{found, selection}``), ``AC_list_views`` (``{found,
views}``) and ``AC_set_view`` (``view``). They are exposed as the matching
``ac_*`` MCP tools (the reads read-only, ``set_view`` destructive) and as Script
Builder commands under **Native UI**.
