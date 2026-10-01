RFC 8288 Link 標頭與分頁
=======================

分頁的 REST API 會回傳 ``Link: <...>; rel="next"`` 標頭,但沒有任何東西解析它,因此多頁抓取需要手動黏合。
本功能解析該標頭(處理含引號的參數值與多個連結)、依關係索引連結,並透過注入的傳輸走訪 ``rel="next"``。

純標準函式庫(``re``);不匯入 ``PySide6``。解析器為純函式,``paginate`` 接受注入的 ``fetch`` callable,
因此分頁可在無線上伺服器的情況下於 CI 測試。

無頭 API
--------

.. code-block:: python

    from je_auto_control import parse_link_header, next_url, links_by_rel, paginate

    header = '<https://api/x?page=2>; rel="next", <https://api/x?page=9>; rel="last"'
    links = parse_link_header(header)            # [Link(uri=..., rel="next"), ...]
    nxt = next_url(header)                        # "https://api/x?page=2"
    last = links_by_rel(header)["last"].uri

    # 透過注入的 fetch(傳輸 / 卡帶)走訪每一頁:
    pages = paginate(start_url, fetch, max_pages=50)

``parse_link_header`` 回傳 ``Link`` 清單(``uri``、``rel`` 與所有 ``params``),以 RFC 8288 附錄 B 的演算法讀取標頭:
引號值保留其中的逗號、分號與跳脫字元，未加引號的值一直到下一個 ``;`` 或 ``,`` 為止(所以 ``title=x<y`` 不會吞掉後面的連結),
沒有值的參數是 ``""``,同名參數以第一次出現為準，遇到第一個不是以 ``<`` 開頭的元素就停止解析。
``links_by_rel`` 依每個關係(以空格與 tab 分隔)索引,``next_url`` 是 ``rel="next"`` 的便利
函式,``paginate`` 抓取一個 URL 並透過提供的 ``fetch`` callable 跟隨 ``next`` 連結,上限為 ``max_pages``。

執行器命令
----------

``AC_parse_link_header`` 把標頭 ``value`` 解析成 ``{links}``;``AC_next_url`` 回傳 ``rel="next"`` 的
``{url}``。兩者皆以 MCP 工具(``ac_parse_link_header`` / ``ac_next_url``)以及 Script Builder 中 **Data**
分類下的命令提供。
