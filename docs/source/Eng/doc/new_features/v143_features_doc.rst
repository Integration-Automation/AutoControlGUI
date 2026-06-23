Composable / Filtered Candidate Locators
=========================================

``anchor_locator`` resolves a single anchor→target relation and ``grid_locator``
addresses grid cells; neither supports *composable refinement* of a candidate set —
``.within(panel).filter(has_text="Delete").nth(2)`` — the Selenium-4 / Playwright
chained-and-filtered locator idiom. Today refining means re-querying a backend. This is
a pure post-filter over boxes from *any* source (template match, OCR, the a11y tree,
:doc:`v138_features_doc`).

A ``Candidates`` wraps a list of ``{x, y, width, height, …}`` boxes; every method
returns a *new* ``Candidates`` so chains are side-effect-free and fully unit-testable.
Pure-stdlib, imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import from_boxes

    target = (from_boxes(boxes)                    # boxes from any locator
              .within((0, 0, 1920, 120))           # only the toolbar
              .filter(has_text="Delete")           # only delete buttons
              .sort_reading()                       # left-to-right
              .nth(1))                              # the second one
    if target.center():
        click(*target.center())

``within(region)`` keeps boxes whose centre is inside the rectangle; ``filter`` keeps
boxes matching every supplied criterion (``has_text`` substring, ``near`` ``(x, y,
max_dist)`` proximity, ``min_area`` / ``max_area``, or an arbitrary ``predicate``);
``sort_reading`` orders them; ``nth`` / ``first`` / ``last`` select; ``resolve()``
returns the surviving list and ``center()`` the first box's centre. Chains never mutate
the original set.

Executor command
----------------

``AC_locate_chain`` applies a JSON list of ``ops`` to a ``boxes`` array in order —
``{op:"within",region:[…]}``, ``{op:"filter",has_text:…}``, ``{op:"reading"}``,
``{op:"nth",index:…}``, ``{op:"first"}``, ``{op:"last"}`` — returning
``{count, boxes, center}``. It is exposed as the MCP tool ``ac_locate_chain`` and as a
Script Builder command under **Image**.
