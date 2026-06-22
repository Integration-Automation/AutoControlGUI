==================================================
New Features (2026-06-19) — Set-of-Marks Overlay
==================================================

Modern GUI agents ground far more reliably when shown a screenshot with
**numbered boxes** over the interactable elements plus an ``id -> bbox``
legend ("Set-of-Marks" prompting): the model picks a *number* instead of
guessing pixel coordinates. This turns AutoControl's existing element
sources into that two-stage "mark then pick a number" loop and resolves the
chosen number back to a click. Pure standard library + Pillow (already a
dependency); wired through the full stack.

.. contents::
   :local:
   :depth: 2


Numbering and the legend
=======================

::

    from je_auto_control import mark_elements, render_marks, resolve_mark

    marks = mark_elements(elements)   # [{id, bbox, center, role, text}, ...]
    legend = [(m["id"], m["text"]) for m in marks]
    annotated_png = render_marks(screenshot_png_bytes, marks)
    chosen = resolve_mark(marks, 3)   # the element the model picked

``mark_elements`` assigns ``1..N`` to every element with a valid bounds and
records its centre; ``render_marks`` draws numbered red boxes on a PNG;
``resolve_mark`` maps a number back to its mark. These are pure and
unit-testable with synthetic elements.


Live "mark then click" loop
==========================

::

    from je_auto_control import mark_screen, mark_click

    result = mark_screen(render_path="marked.png")   # numbers the live a11y tree
    # ... feed result["marks"] + marked.png to a VLM, get back a number ...
    mark_click(3)                                     # click mark #3

``mark_screen`` numbers the live accessibility elements (and optionally
saves a numbered-box overlay screenshot), caching the marks; ``mark_click``
resolves a number from that cache and clicks the element's centre. Exposed
as ``AC_mark_screen`` / ``AC_mark_click`` (and ``ac_mark_screen`` /
``ac_mark_click``).
