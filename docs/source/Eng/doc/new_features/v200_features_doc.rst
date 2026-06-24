Advanced TextPattern — Find / Select / Read Attributes
======================================================

``ax_text`` shipped the three whole-range *reads* (document / selection / visible
text). It could not **search** for a substring, **select** a found range, or read
text **formatting attributes** — needed to assert "the error word is red and
bold" or to place the caret / selection at matched text before typing. This rounds
TextPattern out from "dump the text" to "interrogate and manipulate" it.

* :func:`find_control_text` — whether ``text`` occurs in the control
  (TextPattern.FindText, searches the real content, not OCR),
* :func:`select_control_text` — find ``text`` and select its range, so the next
  keystrokes replace it (FindText + Select),
* :func:`control_text_attributes` — the selection's font / colour formatting.

Each is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam — headless-testable via a fake backend; the real UIA calls live in the
Windows backend. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (find_control_text, select_control_text,
                                 control_text_attributes, type_text)

    if find_control_text("TODO", name="Editor"):
        select_control_text("TODO", name="Editor")    # selection now spans "TODO"
        type_text("DONE")                              # replaces it

    control_text_attributes(name="Editor")
    # {"font_name": "Consolas", "font_size": 11.0, "bold": True,
    #  "italic": False, "foreground_color": 16711680}

``ignore_case`` (default ``True``) controls the search. The control is located by
``name`` / ``role`` / ``app_name`` / ``automation_id`` (same as the other
TextPattern reads). ``find_control_text`` / ``select_control_text`` return
``bool``; ``control_text_attributes`` returns the formatting dict (values may be
``None`` where the range spans mixed formatting) or ``None`` if not found.

Executor commands
-----------------

``AC_find_control_text`` / ``AC_select_control_text`` (``text`` / ``ignore_case``)
and ``AC_control_text_attributes`` (``{found, attributes}``). They are exposed as
the matching ``ac_*`` MCP tools (find / attributes read-only, select destructive)
and as Script Builder commands under **Native UI**.
