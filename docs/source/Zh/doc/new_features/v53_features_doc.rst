DMN 式決策表
============

巢狀的 ``AC_if_var`` 鏈很快就難以閱讀。決策表將分支外部化為一列列的 ``conditions ->
outputs``,並以**命中政策(hit policy)**評估 —— 這是 DMN 讓商業規則維持資料驅動且易於審
查的方式。

每個儲存格條件為萬用字元(``None`` / ``"-"`` / ``"*"``)、字面值(相等)或 ``{"op": "ge",
"value": 18}``,使用本專案標準比較子(``eq/ne/lt/le/gt/ge/contains/startswith/endswith``
—— 重用自執行器,不重複)。純標準函式庫;不匯入 ``PySide6``。

命中政策
--------

================ ===================================================
政策             行為
================ ===================================================
``UNIQUE``       僅可有一條規則命中(多於一條則拋例外)。
``FIRST``        第一條命中的規則勝出。
``PRIORITY``     同 FIRST —— 依規則順序取第一個命中。
``COLLECT``      所有命中規則的 outputs(清單)。
================ ===================================================

無頭 API
--------

.. code-block:: python

    from je_auto_control import evaluate_table

    spec = {
        "inputs": ["age", "country"],
        "hit_policy": "FIRST",
        "rules": [
            {"conditions": {"age": {"op": "lt", "value": 18}},
             "outputs": {"tier": "minor"}},
            {"conditions": {"age": {"op": "ge", "value": 18}, "country": "US"},
             "outputs": {"tier": "us-adult"}},
            {"conditions": {"age": {"op": "ge", "value": 18}},
             "outputs": {"tier": "adult"}},
        ],
    }
    evaluate_table(spec, {"age": 30, "country": "DE"})   # -> {"tier": "adult"}

``evaluate_table`` 對單一命中政策回傳命中的 outputs dict(若無則 ``{}``),``COLLECT`` 則
回傳清單。``DecisionTable`` 類別(``from_dict`` / ``evaluate``)亦可重用。

執行器指令
----------

``AC_decision_table`` 接受 ``spec`` 與 ``context``(各為 dict 或 JSON 字串),回傳
``{result}``。相同操作亦提供為 MCP 工具 ``ac_decision_table``,以及 Script Builder 中
**Flow** 分類下的指令。
