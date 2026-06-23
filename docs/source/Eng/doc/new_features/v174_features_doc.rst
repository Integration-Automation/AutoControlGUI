Paragraph & List Grouping of OCR Lines
======================================

``text_regions.find_text_lines`` merges glyphs into lines, but nothing groups those *lines*
into paragraphs or detects lists — ``ocr/structure`` stops at flat rows. ``text_blocks`` adds
that: ``group_paragraphs`` splits lines into paragraphs wherever the vertical gap exceeds a
multiple of the median line height (the standard whitespace-grouping heuristic), and
``detect_lists`` recognises bulleted / numbered items by their leading marker and left indent.

Pure-stdlib over plain line dicts (text + bbox); fully unit-testable with no image and no OCR
engine. Reuses ``table_grid_fill``'s box-bounds reader. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import group_paragraphs, detect_lists

    for para in group_paragraphs(ocr_lines, line_gap_factor=1.6):
        print(para["n_lines"], para["text"])

    for item in detect_lists(ocr_lines):
        print(item["marker"], item["indent"], item["text"])

``group_paragraphs`` returns paragraph dicts (``left`` / ``top`` / ``right`` / ``bottom`` /
``text`` / ``n_lines``) — a new paragraph begins when the gap from the previous line's bottom
exceeds ``line_gap_factor`` times the median line height. ``detect_lists`` returns the lines
whose text starts with a bullet (``•`` / ``-`` / ``*``) or an ordinal (``1.`` / ``2)`` /
``a.``), each as ``{text, marker, indent, box}`` (``indent`` is the left x, for nesting).

Executor commands
-----------------

``AC_group_paragraphs`` (``lines`` / ``line_gap_factor`` → ``{count, paragraphs}``) and
``AC_detect_lists`` (``lines`` → ``{count, items}``). They are exposed as the MCP tools
``ac_group_paragraphs`` / ``ac_detect_lists`` (read-only) and as the Script Builder commands
**Group Paragraphs** / **Detect Lists** under **OCR**.
