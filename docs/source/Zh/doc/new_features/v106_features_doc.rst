樂觀並行版本儲存
==============

``http_conditional`` 以 ETag 做*讀取*快取(``If-None-Match`` / 304),但從不用於*寫入*並行
(``If-Match`` / 版本檢查)。沒有本地的 compare-and-swap / 版本化記錄儲存來做「只在版本未變時更新」。
本功能補上 ETag 故事的寫入面。

純標準函式庫(``json``);不匯入 ``PySide6``。版本為單調整數,儲存為記憶體內並具 JSON 持久化,因此行為
在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import VersionedStore, VersionConflict, if_match_header

    store = VersionedStore()
    version = store.put("db.host", "prod-1")          # 版本 1
    record = store.get("db.host")                      # {"value": ..., "version": 1}
    try:
        store.put("db.host", "prod-2", expected_version=record["version"])
    except VersionConflict:
        reload_and_retry()
    header = if_match_header(version)                  # HTTP If-Match 用 '"1"'

``put`` 僅在 ``expected_version`` 與當前版本相符時寫入(``0`` 要求鍵不存在,省略則為盲寫)並回傳新版本,
過時寫入時拋出 ``VersionConflict``。``get`` 回傳 ``{value, version}``;``delete`` 同樣受保護;``save`` /
``load`` 以 JSON 持久化。``if_match_header`` / ``check_if_match`` 與 ``http_conditional`` 搭配,橋接到真正的
HTTP ``If-Match`` 寫入。

執行器命令
----------

``AC_cas_put`` 回傳 ``{ok, version}``(衝突時 ``{ok: false, error}``);``AC_cas_get`` 回傳 ``{record}``。
兩者使用具名實例登錄,並以 MCP 工具(``ac_cas_put`` / ``ac_cas_get``)以及 Script Builder 中 **Flow** 分類下
的命令提供。
