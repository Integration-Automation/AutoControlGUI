Wait for Region Colour
======================

``wait_for_pixel`` matches a single point exactly and ``wait_until_pixel_changes``
detects *any* change at one point — neither answers "wait until this status light
turns green", "until the progress bar is mostly filled", or "until the red error
banner is gone". This adds a region-colour wait to the ``smart_waits`` family.

The pixel counting is a pure helper and :func:`wait_until_color` takes an
injectable ``sampler``, so the loop is headless-testable without a real screen.
Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import wait_until_color

    # wait until ≥ 60% of the region is (near) green
    wait_until_color(region=[10, 10, 210, 40], target_rgb=[0, 200, 0],
                     tolerance=15, min_fraction=0.6, timeout_s=20)

    # wait until a red banner disappears
    wait_until_color(region=[0, 0, 800, 60], target_rgb=[200, 0, 0],
                     present=False, timeout_s=10)

Pixels within ``tolerance`` (per channel) of ``target_rgb`` are counted. With
``present=True`` the wait succeeds once that fraction reaches ``min_fraction``;
with ``present=False`` once it drops below it. The result is a ``WaitOutcome``
(``succeeded`` / ``reason`` / ``elapsed_s`` / ``samples_taken``).

Executor commands
-----------------

``AC_wait_color`` takes ``target_rgb`` (and optional ``region``) as JSON arrays
plus ``tolerance`` / ``min_fraction`` / ``present`` / ``timeout_s`` /
``poll_interval_s``, and returns the ``WaitOutcome`` dict. It is exposed as the
MCP tool ``ac_wait_color`` and as a Script Builder command under **Flow**.
