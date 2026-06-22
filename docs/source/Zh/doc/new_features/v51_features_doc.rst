JSONPath 查詢
=============

執行器內建的路徑走訪只會以 ``.`` 切分並索引 —— 無法做萬用字元、遞迴下降或過濾,因此含
陣列的 API/DB 回應很難擷取。``json_query`` 在已解析的 JSON 上加入聚焦的 JSONPath 子集:

================ ===================================================
語法             意義
================ ===================================================
``$``            根(可省略前綴)
``.name``        成員存取
``[n]`` ``[-n]`` 串列索引(負數由尾端起算)
``*`` ``[*]``    萬用字元(所有成員 / 元素)
``..``           遞迴下降
``[?(@.k op v)]`` 過濾陣列元素(``op`` ∈ ``== != < <= > >=``)
================ ===================================================

純標準函式庫(``re``);不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import json_query, json_query_one, json_extract

    json_query(data, "$.store.books[*].title")          # 每個 title
    json_query(data, "$.store.books[?(@.price > 8)].title")  # 過濾
    json_query(data, "$..price")                         # 遞迴下降

    json_query_one(data, "$.user.name", default="?")     # 第一個或預設
    json_extract(data, {"name": "$.user.name",           # 對應 -> 扁平 dict
                        "first_tag": "$.tags[0]"})

``json_query`` 回傳**所有**符合項(清單);``json_query_one`` 回傳第一個(或預設);
``json_extract`` 以 ``{key: path}`` 對應擷取成扁平 dict(每路徑取第一個符合項)。這正是
既有 ``AC_http_to_var`` / API / DB-row 流程所缺的路徑引擎。

執行器指令
----------

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_json_query``                ``{matches}`` —— 符合 JSONPath 的所有值。
``AC_json_extract``              ``{result}`` —— 擷取 ``{key: path}`` 對應。
================================ ===================================================

``data``(與 ``mapping``)接受 JSON 物件或 JSON 字串(因此視覺化建構器可用)。相同操作亦
提供為 MCP 工具(``ac_json_query`` / ``ac_json_extract``),以及 Script Builder 中 **Data**
分類下的指令。
