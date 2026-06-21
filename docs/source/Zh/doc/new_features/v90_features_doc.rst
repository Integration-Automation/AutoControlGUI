HTTP 內容協商與解壓縮
===================

``urllib`` / ``http_request`` 從不設定 ``Accept-Encoding``,也從不解碼 ``Content-Encoding`` 回應,因此
會壓縮的伺服器回傳的內文是原始的;也沒有 quality-value 解析器。本功能加入 ``Accept`` / ``Accept-Encoding``
建構器、q-value 解析器,以及 gzip / deflate 解碼。

純標準函式庫(``gzip`` / ``zlib``);不匯入 ``PySide6``。刻意排除 Brotli(非標準函式庫)。每個函式皆為
純函式,因此在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        build_accept, build_accept_encoding, negotiated_call,
        parse_quality_values, decode_body, build_call,
    )

    call = negotiated_call(
        build_call(url),
        accept=build_accept([("application/json", 1.0), ("text/html", 0.8)]),
        accept_encoding=build_accept_encoding(),
    )
    # ... 執行呼叫,然後:
    body = decode_body(response["headers"], raw_bytes)

    ranked = parse_quality_values("text/html;q=0.8, application/json")
    # [("application/json", 1.0), ("text/html", 0.8)]

``build_accept`` 把媒體型別或 ``(type, q)`` 配對轉成 ``Accept`` 標頭;``build_accept_encoding`` 預設
``gzip, deflate``。``parse_quality_values`` 把 ``Accept`` / ``Accept-Encoding`` 標頭解析成依品質排序的
``(token, q)`` 配對(同分維持順序)。``decode_body`` 依 ``Content-Encoding``(``gzip`` / ``deflate``,含
raw deflate,以及 ``identity``)解壓回應內文,不支援者拋出 ``ValueError``。``negotiated_call`` 把協商標頭
加到 ``build_call`` dict。

執行器命令
----------

``AC_decode_body`` 依 ``headers`` 解碼 base64 的 ``body_base64`` 回傳 ``{body_base64, text}``;
``AC_parse_quality_values`` 回傳 ``{values}``。兩者皆以 MCP 工具(``ac_decode_body`` /
``ac_parse_quality_values``)以及 Script Builder 中 **Data** 分類下的命令提供。
