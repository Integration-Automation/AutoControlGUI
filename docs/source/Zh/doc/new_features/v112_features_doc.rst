地區感知清單格式化
==================

``locale_parse`` 能格式化數字與日期,但依某語言的期望把一串項目串接起來——連接詞、是否有序列(牛津)逗號、
兩項的特例——本身是個獨立的小問題。直接 ``", ".join`` 只會得到 ``"A, B, C"``,沒有「and/or」也沒有在地化。

本功能為少數幾個地區實作 CLDR 的清單樣式組合(start/middle/end 加上兩項樣式),並支援連接(and)/選擇(or)/
單位(unit)樣式。純標準函式庫;不匯入 ``PySide6``。每個函式皆為純函式,因此在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import format_list

    format_list(["apple", "pear", "grape"])               # 'apple, pear, and grape'
    format_list(["apple", "pear", "grape"], style="or")   # 'apple, pear, or grape'
    format_list(["apple", "pear"], style="unit")          # 'apple, pear'
    format_list(["manzana", "pera", "uva"], locale="es")  # 'manzana, pera y uva'
    format_list(["A", "B", "C", "D"], locale="fr")        # 'A, B, C et D'

``style`` 為 ``"and"``(連接)、``"or"``(選擇)或 ``"unit"``(僅以逗號分隔、無連接詞)。``locale`` 選擇連接詞與
序列逗號規則(``en`` / ``es`` / ``fr`` / ``de`` / ``pt``;英文使用牛津逗號,其餘不使用;未知地區回退為英文)。
一項、兩項與空清單皆以特例處理。未知的 ``style`` 會拋出 ``ValueError``。

執行器命令
----------

``AC_format_list`` 接受 JSON 陣列並回傳 ``{text}``,可帶 ``style`` 與 ``locale``。它以 MCP 工具
``ac_format_list`` 以及 Script Builder 中 **Data** 分類下的命令提供。
