multipart/form-data 建立與解析
=============================

``http_request`` 只送出 JSON 或原始內文 —— 沒有檔案上傳,而曾經能解析 multipart 的標準函式庫 ``cgi``
模組已在 Python 3.13 移除。本功能以決定性的 boundary 從文字欄位與檔案組裝 ``multipart/form-data``
內文,並能將其解析回來。

純標準函式庫(``re`` / ``secrets``);不匯入 ``PySide6``。boundary 可注入,因此建立出的內文位元組穩定、
可於 CI 測試。

無頭 API
--------

.. code-block:: python

    from je_auto_control import build_multipart, parse_multipart, MultipartFile

    content_type, body = build_multipart(
        fields={"title": "Q3 report"},
        files=[MultipartFile("file", "report.csv", csv_text, "text/csv")],
    )
    http_request(url, method="POST",
                 headers={"Content-Type": content_type}, data=body)

    parsed = parse_multipart(content_type, body)   # {"fields": {...}, "files": [...]}

``build_multipart`` 接受 ``fields``(dict 或 ``(name, value)`` 清單)與 ``files``(``MultipartFile``
實例或 ``{name, filename, content, content_type?}`` dict),回傳 ``(content_type, body_bytes)``。傳入明確
的 ``boundary`` 可得位元組穩定的內文,或呼叫 ``new_boundary`` 取得新 token。``parse_multipart`` 把內文讀回
``{fields, files}``(每個檔案為 ``{name, filename, content_type, content}``)。

執行器命令
----------

``AC_build_multipart`` 對 ``fields`` / ``files``(以及選用 ``boundary``)回傳 ``{content_type,
body_base64}``;``AC_parse_multipart`` 接受 ``content_type`` 與 ``body_base64`` 回傳 ``{fields, files}``。
兩者皆以 MCP 工具(``ac_build_multipart`` / ``ac_parse_multipart``)以及 Script Builder 中 **Data** 分類下
的命令提供。
