參照完整性檢查
============

``data_quality.validate_rows`` 嚴格限於單列、單表 —— 它的 ``unique`` 規則只在單一批次內去重。沒有跨兩個
已載入資料表的父子外鍵檢查、沒有複合鍵唯一性,也沒有獨立的 accepted-values / row-count 斷言。本功能在
已由 ``load_rows`` / ``query_sqlite`` 載入的資料列上,補上這些 dbt 風格的通用檢查。

純標準函式庫(``collections``);不匯入 ``PySide6``。每個函式皆為純函式(輸入列、輸出報告),因此在 CI
中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        check_foreign_key, check_unique_key, check_accepted_values,
        check_row_count, load_rows,
    )

    orders = load_rows("orders.csv")
    users = load_rows("users.csv")

    fk = check_foreign_key(orders, "user_id", users, "id")   # {ok, violations, missing}
    pk = check_unique_key(orders, ["region", "id"])          # {ok, duplicates}
    av = check_accepted_values(orders, "status", ["open", "closed"])
    rc = check_row_count(orders, minimum=1)                  # {ok, count}

``check_foreign_key`` 標記父欄位中不存在的非空子值(dbt ``relationships``)。``check_unique_key`` 回報
重複的單一或複合鍵。``check_accepted_values`` 列出允許集合之外的非空值。``check_row_count`` 驗證筆數
落在選用的 ``minimum`` / ``maximum`` 範圍內。每個皆回傳 ``ok`` 旗標加上細節。

執行器命令
----------

``AC_check_foreign_key``、``AC_check_unique_key``、``AC_check_accepted_values`` 與 ``AC_check_row_count``
各自接受 JSON ``rows``(以及欄位 / 鍵 / 允許清單)並回傳報告。全部皆以 MCP 工具(``ac_check_*``)以及
Script Builder 中 **Data** 分類下的命令提供。
