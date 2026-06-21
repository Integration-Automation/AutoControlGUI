Feature Flags
=============

``decision_table`` is a one-shot DMN evaluator and ``ab_locator`` measures
locator outcomes — neither is a product feature-flag store with sticky
percentage rollout. This adds an OpenFeature-shaped flag engine: typed flags
with targeting rules, weighted variants, a kill switch, and consistent-hash
bucketing so a given subject always lands in the same variant.

Pure standard library (``hashlib`` + ``re`` + ``json``); deterministic; imports
no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import FlagStore, evaluate_flag, is_enabled

    store = FlagStore.from_dict({"flags": {
        "new-checkout": {
            "variants": {"on": True, "off": False},
            "default_variant": "off", "off_variant": "off",
            "targeting": [
                {"conditions": {"country": {"op": "in", "value": ["US", "CA"]}},
                 "serve": "on"},
                {"conditions": {"plan": {"op": "eq", "value": "premium"}},
                 "serve": {"rollout": {"on": 50, "off": 50}}},
            ],
            "fallthrough": {"rollout": {"on": 10, "off": 90}},
        },
    }})

    evaluate_flag(store, "new-checkout", {"country": "US"})
    # {"flag_key": "new-checkout", "variant": "on", "value": True,
    #  "reason": "TARGETING_MATCH"}

    if is_enabled(store, "new-checkout", {"targeting_key": "user-123"}):
        ...

Evaluation order mirrors OpenFeature/Unleash/LaunchDarkly: a disabled flag
serves ``off_variant`` (reason ``DISABLED``); an unknown flag returns the
caller default (reason ``ERROR``); targeting rules are tried in order
(``TARGETING_MATCH``); otherwise the fallthrough applies (``DEFAULT`` /
``SPLIT``). Targeting operators include ``eq``/``ne``/``lt``/``gt``/``in``/
``not_in``/``contains`` and ``semver_*``. Percentage rollout is a
consistent-hash bucket of ``sha256("{key}.{salt}.{context_key}")`` so a subject
is **sticky** — it always gets the same variant. ``percentage_bucket`` and
``assign_variant`` are exposed for direct use.

Executor commands
-----------------

``AC_evaluate_flag`` takes ``flags`` (a store mapping or JSON string), a
``key`` and optional ``context``; it returns ``{value, variant, reason}``.
``AC_flag_enabled`` returns ``{enabled}``. Both are exposed as MCP tools
(``ac_evaluate_flag`` / ``ac_flag_enabled``) and as Script Builder commands
under **Flow**.
