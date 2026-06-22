功能旗標(Feature Flags)
========================

``decision_table`` 是一次性的 DMN 評估器,``ab_locator`` 衡量定位器成效 —— 兩者都不是帶有黏性
百分比推出的產品功能旗標儲存庫。本功能補上 OpenFeature 形狀的旗標引擎:具型別的旗標、目標規則、
加權變體、kill switch,以及一致雜湊分桶,讓同一主體永遠落在同一變體。

純標準函式庫(``hashlib`` + ``re`` + ``json``);具決定性;不匯入 ``PySide6``。

無頭 API
--------

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

評估順序對齊 OpenFeature/Unleash/LaunchDarkly:停用的旗標提供 ``off_variant``(原因
``DISABLED``);未知旗標回傳呼叫端預設(原因 ``ERROR``);目標規則依序嘗試(``TARGETING_MATCH``);
否則套用 fallthrough(``DEFAULT`` / ``SPLIT``)。目標運算子包含 ``eq``/``ne``/``lt``/``gt``/
``in``/``not_in``/``contains`` 與 ``semver_*``。百分比推出是
``sha256("{key}.{salt}.{context_key}")`` 的一致雜湊分桶,因此主體具**黏性** —— 永遠得到相同變體。
``percentage_bucket`` 與 ``assign_variant`` 亦可直接使用。

執行器命令
----------

``AC_evaluate_flag`` 接受 ``flags``(store 對映或 JSON 字串)、``key`` 與選用的 ``context``,回傳
``{value, variant, reason}``。``AC_flag_enabled`` 回傳 ``{enabled}``。兩者皆以 MCP 工具
(``ac_evaluate_flag`` / ``ac_flag_enabled``)以及 Script Builder 中 **Flow** 分類下的命令提供。
