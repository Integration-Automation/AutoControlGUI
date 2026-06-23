Heading vs Body Classification + Document Outline
=================================================

Nothing in the framework maps line height to heading levels or builds a section outline —
``ocr/structure`` and ``element_parse`` are purely positional, and ``text_blocks`` groups
paragraphs / lists but does not rank them. ``heading_segment`` adds the standard heuristic:
a line whose height exceeds ``heading_ratio`` times the median line height is a heading, and
distinct heading heights become heading *levels* (the tallest is level 1). From that it emits
a flat document outline.

Pure-stdlib over plain line dicts (text + bbox); fully unit-testable with no image and no OCR
engine. Reuses ``table_grid_fill``'s box-bounds reader. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import classify_lines, outline

    for item in classify_lines(ocr_lines, heading_ratio=1.2):
        print(item["role"], item["level"], item["text"])

    for heading in outline(ocr_lines):
        print("  " * (heading["level"] - 1) + heading["text"])

``classify_lines`` tags each line ``{box, text, role, level}`` — ``role`` is ``"heading"`` or
``"body"``, ``level`` is the heading level (1 = tallest, 0 for body). ``outline`` returns just
the headings in top-to-bottom order as ``{level, text, top}`` — a document table of contents.

Executor commands
-----------------

``AC_classify_lines`` (``lines`` / ``heading_ratio`` → ``{count, lines}``) and ``AC_outline``
(``lines`` / ``heading_ratio`` → ``{count, headings}``). They are exposed as the MCP tools
``ac_classify_lines`` / ``ac_outline`` (read-only) and as the Script Builder commands
**Classify Headings vs Body** / **Document Outline** under **OCR**.
