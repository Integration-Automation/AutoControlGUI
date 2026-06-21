Cookie Jar(HTTP 工作階段攜帶)
=============================

``http_request`` 無狀態 —— 沒有任何工作階段 cookie 會在呼叫間延續,因此 login-then-call 的 REST 流程
無法在無頭情況下攜帶工作階段。本功能把 ``Set-Cookie`` 回應標頭解析進一個 jar 並建立 ``Cookie`` 請求標頭;
jar 可序列化為 JSON,因此工作階段可存檔與重新載入。

純標準函式庫(``json``);不匯入 ``PySide6``。jar 為簡單的記憶體內名稱-值儲存(``Max-Age<=0`` / 空值時
清除 cookie),因此行為在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import CookieJar, parse_set_cookie

    jar = CookieJar()
    jar.update(login_response_set_cookie_headers)   # str 或 Set-Cookie 清單
    cookie = jar.cookie_header()                     # "sid=abc; theme=dark"
    # 後續請求把 `cookie` 當作 Cookie 標頭送出

    jar.save("session.json")
    jar = CookieJar.load("session.json")

``parse_set_cookie`` 把單一 ``Set-Cookie`` 值解析成 ``{name, value, attributes}``。``CookieJar.update``
套用一或多個 ``Set-Cookie`` 標頭(空值或 ``Max-Age<=0`` 時移除 cookie);``set`` 直接指定;``cookie_header``
建立請求標頭;``to_dict`` / ``from_dict`` 與 ``save`` / ``load`` 以 JSON 持久化 jar。(網域/路徑比對為簡化版
—— 這是工作階段攜帶用的 jar,而非完整 RFC 6265 政策引擎。)

執行器命令
----------

``AC_cookie_header`` 從一或多個 ``set_cookies`` 建立 ``{cookie_header, cookies}``;``AC_parse_set_cookie``
對單一標頭回傳 ``{cookie}``。兩者皆以 MCP 工具(``ac_cookie_header`` / ``ac_parse_set_cookie``)以及
Script Builder 中 **Data** 分類下的命令提供。
