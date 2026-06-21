資料剖析與結構推斷
================

``data_quality.validate_rows`` *消費* 一份手寫結構,``stats.describe`` 只彙總單一數值清單 —— 沒有任何
東西能掃描整個資料列集合,回報每欄的空值比例、基數、推斷型別、值域與最常見值,也無法提出一份起始結構。
本功能補上這個剖析步驟,並餵給既有的驗證器。

純標準函式庫(``collections`` + 重用 ``stats``);不匯入 ``PySide6``。每個函式皆為純函式(輸入列、輸出
dict),因此在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import profile_rows, infer_schema, validate_rows, load_rows

    rows = load_rows("export.csv")
    profile = profile_rows(rows)
    # profile["columns"]["age"] -> {count, null_count, null_fraction, distinct,
    #   unique, inferred_type, top_values, min, max, mean}

    schema = infer_schema(rows)        # validate_rows 相容
    report = validate_rows(rows, schema)

``profile_rows`` 回傳 ``{row_count, columns}``,每欄帶有其筆數、空值數與比例、相異值數、唯一性旗標、
推斷型別(``int`` / ``number`` / ``bool`` / ``str``)、最常見值與其次數,以及數值欄的 ``min`` /
``max`` / ``mean``。``infer_schema`` 把該剖析轉成既有 ``validate_rows`` 能理解的結構:無空值的欄位
標為 ``required``,每個非空值皆相異則標為 ``unique``,並帶上數值邊界。傳入明確的 ``columns`` 清單可將
兩個函式限制在子集。

執行器命令
----------

``AC_profile_rows`` 剖析 ``rows`` 清單(可選 ``columns`` 子集)回傳 ``{profile}``。``AC_infer_schema``
回傳 ``{schema}``。兩者皆以 MCP 工具(``ac_profile_rows`` / ``ac_infer_schema``)以及 Script Builder
中 **Data** 分類下的命令提供。
