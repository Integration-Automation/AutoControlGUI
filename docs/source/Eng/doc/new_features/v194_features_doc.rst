Per-Run Step Timeline (waterfall + bottleneck steps)
====================================================

The action profiler aggregates timings by step *name* across many runs — great
for "which action is slow on average", useless for "why was *this* run slow". A
single run is an ordered timeline: step A ran, then B, then C, and one of them
dominated. ``step_timeline`` turns one run's steps into a waterfall (each step's
offset from the start, its duration and its share of the total) and ranks the
bottleneck steps, so you can read a single slow run instead of an average.

* :func:`build_timeline` — the waterfall + total / busy / bottleneck /
  parallelism,
* :func:`critical_steps` — the steps that dominate the run, longest first.

A step is any dict with a name (default ``"name"``) and a ``duration``; an
optional ``start`` places it on an absolute timeline (overlapping / parallel
steps), else steps are laid out back-to-back. Pure standard library; no device,
no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import build_timeline, critical_steps

    steps = [{"name": "login", "duration": 1.0},
             {"name": "load_dashboard", "duration": 4.0},
             {"name": "submit", "duration": 1.0}]

    build_timeline(steps)
    # {"steps": [{"name": "login", "offset": 0.0, "duration": 1.0, "pct": 16.7},
    #            {"name": "load_dashboard", "offset": 1.0, ..., "pct": 66.7}, ...],
    #  "total": 6.0, "busy": 6.0,
    #  "bottleneck": {"name": "load_dashboard", "duration": 4.0},
    #  "parallelism": 1.0}

    critical_steps(steps, top=2)
    # [{"name": "load_dashboard", "duration": 4.0, "pct": 66.7},
    #  {"name": "login", "duration": 1.0, "pct": 16.7}]

``total`` is the wall-clock span, ``busy`` the summed step time; ``parallelism`` =
busy / total is ``1.0`` for a purely sequential run and ``> 1`` when steps overlap
(supply ``start`` times). ``pct`` is each step's share of the total time.

Executor commands
-----------------

``AC_build_timeline`` (``steps``) and ``AC_critical_steps`` (``steps`` / ``top``).
They are exposed as read-only ``ac_*`` MCP tools and as Script Builder commands
under **Testing**.
