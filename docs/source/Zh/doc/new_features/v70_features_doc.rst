JSON 合約與快照比對
===================

``json_schema`` 以撰寫的 schema 驗證一個值,``jsonpath`` 擷取值,但沒有任何東西能以寬鬆規則
(僅型別、部分、忽略易變路徑)比對兩份 JSON *內容*,或逐路徑對它們取差異以做合約 / 快照測試。
本功能補上這個層;它與 ``json_schema``(形狀)及 ``json_patch``(結構化編輯)互補。

純標準函式庫(``json``);具決定性;不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import match_json, diff_json, snapshot

    report = match_json(actual, {"id": 1, "name": "Ada"})
    if not report.ok:
        for m in report.mismatches:
            print(m["path"], m["kind"])     # 例如 "$.name" "changed"

    # Pact 風格的 "like":值可不同,但型別必須相符
    match_json(response, template, match_type=True)
    # 子集比對:允許 actual 有額外的鍵
    match_json(response, template, partial=True)
    # 忽略易變欄位
    match_json(response, template, ignore=["$.created_at", "$.id"])

    diff_json(actual, expected)              # [{path, kind, ...}]
    snapshot(actual, "golden/checkout.json")  # 不存在則寫入,否則比對

``match_json`` 回傳 ``MatchReport(ok, mismatches)``,每個不符為 ``{path, kind}``,``kind`` 為
``missing``(在 expected、actual 沒有)、``extra``(在 actual、expected 沒有)或 ``changed`` 之一。
選項:``partial`` 捨棄 ``extra`` 不符(子集比對),``match_type`` 接受型別相符的 ``changed`` 葉
(Pact ``like``),``ignore`` 略過列出的路徑。``diff_json`` 是原始的路徑標記差異;``normalize_json``
回傳正規化副本(鍵排序、移除 ``drop`` 鍵)以利穩定比對;``snapshot`` 是 golden-master 測試
(首次執行寫檔,之後比對)。``true`` 與 ``1`` 保持相異。

執行器命令
----------

``AC_match_json`` 接受 ``actual`` / ``expected``(物件或 JSON 字串)及選用的 ``partial`` /
``match_type``,回傳 ``{ok, mismatches}``。``AC_diff_json`` 回傳 ``{diffs}``。兩者皆以 MCP 工具
(``ac_match_json`` / ``ac_diff_json``)以及 Script Builder 中 **Data** 分類下的命令提供。
