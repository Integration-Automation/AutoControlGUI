Pre-Action Grounding Guard
==========================

``guardrail`` scans text for prompt-injection and ``loop_guard`` detects stuck loops —
but neither validates a *coordinate action* before it is dispatched. An agent loop
executes whatever the model returns with no bounds or target check, so a hallucinated
``(9999, -5)`` click fires into nothing and a 5-pixel-off click misses the button.
``validate_action`` adds the "detect misaligned actions before execution" guard: reject
clicks outside the screen and snap a near-miss coordinate onto the nearest known
element's centre.

Pure-stdlib geometry over plain element dicts (``x`` / ``y`` / ``width`` / ``height``),
so it is fully unit-testable. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import validate_action, snap_to_element, in_bounds

    check = validate_action(model_action, screen_size=(1920, 1080), targets=elements)
    if not check["ok"]:
        print("rejected:", check["reason"])         # e.g. "out of bounds"
    else:
        x, y = check["snapped"] or (model_action["x"], model_action["y"])
        click(x, y)                                  # snapped onto the real button

``in_bounds(x, y, screen_size)`` is the screen-bounds predicate; ``snap_to_element``
returns the centre of the element at (or nearest within ``max_dist`` of) a point, or
``None``; ``validate_action`` combines them, returning ``{ok, reason, snapped}`` —
rejecting out-of-bounds coordinates and snapping near-misses when ``targets`` are
supplied. Actions without a coordinate always pass.

Executor command
----------------

``AC_validate_action`` (``action`` / ``screen`` / ``targets`` → ``{ok, reason,
snapped}``; ``screen`` defaults to the live screen). It is exposed as the MCP tool
``ac_validate_action`` and as a Script Builder command under **Native UI**.
