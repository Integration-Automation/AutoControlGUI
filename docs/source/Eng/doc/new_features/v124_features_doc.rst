Anchor Ordinal & Locate-All
===========================

``anchor_locate`` finds a target by spatial relation to an anchor but always
returned the single *nearest* match — there was no way to pick "the **2nd** row
below the header" or to enumerate every matching row. This adds an ``ordinal``
selector and a list-returning :func:`anchor_locate_all`.

Both build on a shared ranking helper (pure: filter by relation, sort by
distance) so the selection logic is unit-testable by injecting candidate boxes.
Headless and Qt-free.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        anchor_locate, anchor_locate_all, ocr_locator, image_locator,
    )

    header = ocr_locator("Name")
    row = image_locator("row_handle.png")

    anchor_locate(anchor=header, target=row, relation="below")             # nearest
    anchor_locate(anchor=header, target=row, relation="below", ordinal=2)  # 2nd row
    rows = anchor_locate_all(anchor=header, target=row, relation="below")  # all rows

``ordinal`` is 1-based (``ordinal=1`` is the nearest, the previous behaviour, so
this is backward-compatible); an out-of-range ordinal returns a not-found outcome.
``anchor_locate_all`` returns a list of found ``AnchorOutcome`` ordered by
distance — the building block for table / list-row selection.

Executor commands
-----------------

``AC_anchor_locate`` gains an ``ordinal`` parameter; ``AC_anchor_locate_all``
returns ``{count, matches}``. Both are exposed as MCP tools (``ac_anchor_locate``
with ``ordinal`` / ``ac_anchor_locate_all``).
