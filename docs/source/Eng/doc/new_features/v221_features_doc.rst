Act In View — Scroll to a Target, Then Act When Actionable
==========================================================

Two reliability primitives stayed separate: ``scroll_find.scroll_until_visible``
brings an off-screen target on-screen, and ``actionability.act_when_ready`` waits
for a target to be visible / stable / enabled / unoccluded before acting. A real
"click the row three pages down" step needs *both* — scroll to it, then gate
before clicking. ``act_in_view`` composes them into one call.

* :class:`ScrollPlan` — bundles the scroll search (``kind`` / ``direction`` /
  ``max_scrolls`` / ``scroll_amount``) and its injectable ``locator`` /
  ``scroller`` seams, so the composed call stays within a sane argument count.
* :func:`act_in_view` — scroll until the target is found, then run the
  actionability gate at its location and perform ``action`` on it.

Every seam — the scroll locator / scroller, the action, the actionability probes
(``region_sampler`` / ``enabled_probe`` / ``hit_tester``) and the gate ``config``
— is injectable, so the whole flow is testable without a screen. Reuses
:func:`scroll_find.scroll_until_visible` and
:func:`actionability.act_when_ready`. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import act_in_view, ScrollPlan

    # Scroll down to the "Submit" button image, then click it once it's actionable
    act_in_view("submit.png", lambda point: click(point[0], point[1]),
                scroll=ScrollPlan(kind="image", direction="down",
                                  max_scrolls=20))

``act_in_view`` returns ``{acted, coords, scrolls, result}`` (``result`` is the
action's return value) and raises ``AutoControlActionException`` if the target
never comes into view. Pass ``enabled_probe`` / ``hit_tester`` / ``config`` to
have the actionability gate actually wait for the control to be enabled and
unoccluded before the action fires — otherwise it acts as soon as the target is
located.

Executor commands
-----------------

``AC_act_in_view`` (``target`` + ``kind`` / ``direction`` / ``max_scrolls`` /
``scroll_amount`` / ``button`` → ``{acted, coords, scrolls}``) scrolls a template
or text target into view and clicks it. It is the matching ``ac_act_in_view`` MCP
tool and a Script Builder command under **Flow**. :func:`act_in_view` (which
takes an arbitrary action and the actionability probes) is the Python-API
surface.
