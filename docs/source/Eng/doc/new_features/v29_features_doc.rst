==================================================
New Features (2026-06-19) — Tweened Drag
==================================================

Deterministic eased drags along a curved path (PyAutoGUI-style ``tween``),
complementing the existing humanized jitter. Pure standard library; full
stack. The point math is pure and unit-testable; dispatch goes through an
injectable sink.

.. contents::
   :local:
   :depth: 2


Usage
=====

::

    from je_auto_control import tween_points, tween_drag, easing_names

    tween_points((0, 0), (100, 50), steps=20, easing="ease_out_cubic")
    tween_drag((0, 0), (300, 200), steps=40, easing="ease_in_out_quad")

``tween_points`` returns ``steps + 1`` eased points between two
coordinates; ``tween_drag`` presses at the start, moves through the points,
and releases at the end. Easings: ``linear`` / ``ease_in_out_quad`` /
``ease_out_cubic`` / ``ease_in_cubic`` (see :func:`easing_names`). Exposed
as ``AC_tween_drag`` / ``ac_tween_drag`` (``start`` / ``end`` as ``[x, y]``).

Pacing, for apps that tell a drag from a click by the pointer's motion
(file managers, drawing programs, games)::

    tween_drag((0, 0), (300, 200), steps=24, step_delay_s=0.012, settle_s=0.08)

``step_delay_s`` rests after each move; ``settle_s`` rests on the start
before the press, after the press and before the release. Both default to
0 (no pause) and must be finite and non-negative. If a step raises, the
button is released in a ``finally`` at the last point the pointer reached,
not at the end, and the original error propagates.
