條件式 HTTP 請求與快取驗證子
========================

``http_request`` 從不送出 ``If-None-Match`` / ``If-Modified-Since`` 也不讀取 ``Cache-Control``,因此每次
輪詢都會重新下載未變更的資源。本功能從回應擷取快取驗證子、解析 ``Cache-Control``、判定新鮮度,並為下一個
請求加上條件標頭,讓伺服器可回應 ``304 Not Modified``。

純標準函式庫;不匯入 ``PySide6``。新鮮度判定接受明確的 age(不使用 wall clock),因此邏輯在 CI 中完全
具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        store_validators, conditioned_call, is_fresh, is_not_modified,
        parse_cache_control, build_call,
    )

    response = http_request(url)
    validators = store_validators(response)
    if is_fresh(validators, age_seconds=now - stored_at):
        use_cached()
    else:
        revalidation = conditioned_call(build_call(url), validators)
        fresh = perform(revalidation)
        if is_not_modified(fresh):
            use_cached()           # 304 → 已儲存的內文仍有效

``store_validators`` 從回應取出 ``etag`` / ``last_modified`` / ``date`` 與解析後的 ``cache_control``。
``parse_cache_control`` 把標頭轉成 directive dict(``max-age`` 為 int,旗標為 ``True``)。``conditioned_call``
把 ``If-None-Match`` / ``If-Modified-Since`` 加到 ``build_call`` dict。``is_fresh`` 在給定 age 下回報快取項
是否仍新鮮(``no-store`` / ``no-cache`` 永不新鮮)。``is_not_modified`` 偵測 ``304`` 回應。

執行器命令
----------

``AC_parse_cache_control`` 對 ``headers`` 回傳 ``{directives}``;``AC_store_validators`` 對 ``response``
回傳 ``{validators}``。兩者皆以 MCP 工具(``ac_parse_cache_control`` / ``ac_store_validators``)以及
Script Builder 中 **Data** 分類下的命令提供。
