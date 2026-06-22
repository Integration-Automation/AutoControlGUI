Agent Trajectory Evaluation
===========================

As automations hand control to LLM agents, "did it still work?" becomes "did
the agent take an acceptable path?". :func:`evaluate_trajectory` scores a
recorded run against a declarative **rubric**, giving a deterministic,
dependency-free signal for agent regression testing.

A *trajectory* is the ordered list of steps a run took — each a dict with at
least an ``"action"`` name and optionally ``"args"`` / ``"observation"``. The
*rubric* is plain data (so it lives happily in a JSON action file or arrives
over MCP):

================================ ===================================================
Rubric key                       Meaning
================================ ===================================================
``required_actions``             Actions that must all appear.
``ordered``                      With the above, also require that relative order.
``forbidden_actions``            Actions that must never appear.
``max_steps``                    Upper bound on trajectory length.
``success_contains``             Substring that must appear in some observation.
================================ ===================================================

Headless API
------------

.. code-block:: python

    from je_auto_control import evaluate_trajectory

    trajectory = [
        {"action": "AC_focus_window", "observation": "focused"},
        {"action": "AC_type_text", "observation": "typed"},
        {"action": "AC_click_mouse", "observation": "Saved successfully"},
    ]
    result = evaluate_trajectory(trajectory, {
        "required_actions": ["AC_type_text", "AC_click_mouse"],
        "forbidden_actions": ["AC_kill_process"],
        "max_steps": 10,
        "success_contains": "Saved",
    })
    assert result["passed"]            # every applicable check passed
    print(result["score"], result["checks"])

``score`` is the fraction of applicable checks that passed; ``passed`` is true
only when all pass; an empty rubric trivially passes. Each entry in ``checks``
is ``{name, passed, detail}`` so a failure pinpoints the violated expectation.

Executor command
----------------

``AC_evaluate_trajectory`` takes ``trajectory`` and ``rubric`` (each a JSON
string from the visual builder, or already-decoded data from a JSON action file
/ MCP) and returns ``{passed, score, steps, checks}``. The same operation is
exposed as the MCP tool ``ac_evaluate_trajectory`` and as a Script Builder
command under **Agent**.
