Run-Trace Diff (what changed between two executions)
====================================================

A run history tells you a run *failed*, but not *what changed* from the run that
passed: which step was added or dropped, which step flipped pass→fail, which step
got slower. ``run_diff`` aligns the two step sequences with a longest-common-
subsequence walk — so an inserted or removed step shifts the rest into place
instead of mis-pairing everything — and classifies the differences:

* **added** / **removed** — steps present in only one run,
* **status_flips** — an aligned step whose status changed, with the new failure's
  :func:`failure_signature` when it carries an ``error``,
* **timing_regressions** — an aligned step that got ``regress_factor`` x slower.

A step is any dict with a name key (default ``"name"``) and optional ``status`` /
``duration`` / ``error``. Pure standard library; no device, no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import diff_runs, summarize_run_diff

    before = [{"name": "login", "status": "ok", "duration": 1.0},
              {"name": "submit", "status": "ok", "duration": 1.0}]
    after = [{"name": "login", "status": "ok", "duration": 1.1},
             {"name": "accept_cookies", "status": "ok"},          # inserted
             {"name": "submit", "status": "error", "error": "Timeout ..."}]

    diff = diff_runs(before, after)
    # {"added": [accept_cookies], "removed": [],
    #  "status_flips": [{"name": "submit", "from": "ok", "to": "error",
    #                    "signature": "..."}],
    #  "timing_regressions": [], "aligned": 2, "identical": False}

    summarize_run_diff(diff)        # "+1 added, 1 status flip(s)"

``regress_factor`` (default ``1.5``) is the slowdown ratio that counts as a
regression; ``key`` selects the field steps are aligned on. ``summarize_run_diff``
renders a one-line summary (``"no change"`` when identical).

Executor commands
-----------------

``AC_diff_runs`` (``before`` / ``after`` / ``key`` / ``regress_factor``) returns
the diff plus a ``summary`` field. It is exposed as the read-only ``ac_diff_runs``
MCP tool and as a Script Builder command under **Testing**.
