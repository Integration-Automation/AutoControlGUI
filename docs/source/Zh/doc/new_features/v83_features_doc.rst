資料集差異(資料列變更報告)
========================

框架能比對*畫面/快照*(``screen_state.diff_snapshots``、``diff_screenshots``),但沒有任何東西能依
鍵比對兩個**表格式**資料列集合 —— 也就是經典的「今天的萃取相較昨天變了什麼」報告。本功能為兩側建立
鍵索引,再回報新增 / 刪除 / 變更 / 未變更的資料列以及逐欄變更。

純標準函式庫;不匯入 ``PySide6``。每個函式皆為純函式(輸入列、輸出 dict/list),因此在 CI 中完全
具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import diff_rows, cell_changes, summarize_diff, load_rows

    old = load_rows("yesterday.csv")
    new = load_rows("today.csv")

    diff = diff_rows(old, new, "id")          # 或 ["region", "id"]
    summarize_diff(diff)                       # {added, removed, changed, unchanged}

    for change in cell_changes(old, new, "id"):
        print(change["key"], change["column"], change["old"], "->", change["new"])

``diff_rows`` 為兩個資料列集合建立鍵索引,回傳 ``{added, removed, changed, unchanged}``:``added`` /
``removed`` / ``unchanged`` 是資料列清單,而 ``changed`` 收錄 ``{key, old, new}``(單欄鍵為純量,複合鍵
為 list)。鍵重複時以最後一列為準。``cell_changes`` 把變更的列展開成 ``{key, column, old, new}`` 記錄。
``summarize_diff`` 統計每個分類的數量。

執行器命令
----------

``AC_diff_rows`` 對 ``old_rows`` / ``new_rows`` 與 ``key``(欄名或 JSON 清單)回傳 ``{diff, summary}``。
``AC_cell_changes`` 回傳 ``{changes}``。兩者皆以 MCP 工具(``ac_diff_rows`` / ``ac_cell_changes``)以及
Script Builder 中 **Data** 分類下的命令提供。
