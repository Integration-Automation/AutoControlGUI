Per-Step Critic Features + Rule-Based Step Scorer
=================================================

Scoring an agent's step needs the evidence in one place — what the action was, what changed,
whether it landed on target, whether the declared postcondition held. ``trajectory_eval``
scores a *finished whole trajectory* against a static rubric and has no per-step evidence;
``agent_trace`` emits OTel spans (tokens / latency), not decision quality; ``agent_replay``
persists ``{obs, action, result}`` but does no scoring. ``critic_features`` is the missing
per-step layer: it composes ``action_effect`` (did it do anything, where),
``observation_delta`` (how much changed) and ``postcondition`` (did the expected outcome hold)
into one compact record, and ships a deterministic rule-based scorer so the feature works fully
headless — leaving the optional LLM-as-judge to the integrator.

Pure-stdlib; composes existing pure modules; deterministic and unit-testable with no device.
Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (build_critic_record, score_step_rule_based,
                                 to_judge_prompt)

    record = build_critic_record({"type": "click", "x": 480, "y": 260},
                                 before_elements, after_elements,
                                 postcondition={"appears": {"role": "dialog"}})
    score = score_step_rule_based(record)
    # {"outcome": True, "process_score": 1.0, "reasons": [...]}

    prompt = to_judge_prompt(record)   # compact text for an LLM-as-judge

``build_critic_record`` returns ``{action, effect, delta_counts}`` plus a ``postcondition``
report when a spec is given. ``score_step_rule_based`` returns ``{outcome, process_score,
reasons}`` — ``outcome`` is a binary success (the action did something *and* any postcondition
held), ``process_score`` is a 0..1 quality from the effect class (halved if the postcondition
failed). ``to_judge_prompt`` renders the record for an external judge.

Executor commands
-----------------

``AC_build_critic_record`` (``action`` / ``before`` / ``after`` / ``postcondition`` /
``radius`` → the record) and ``AC_score_step`` (``record`` → ``{outcome, process_score,
reasons}``). They are exposed as the MCP tools ``ac_build_critic_record`` / ``ac_score_step``
(read-only) and as the Script Builder commands **Build Critic Record** / **Score Step
(rule-based)** under **Native UI**.
