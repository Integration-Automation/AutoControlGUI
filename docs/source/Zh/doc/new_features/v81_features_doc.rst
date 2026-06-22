分層設定解析器
============

``json_patch.merge_patch`` 只合併兩份文件,``config_sync`` 以 last-write-wins 時間戳解析,
``AssetStore`` 則是每環境的扁平結構。它們都無法組成一個有序的 ``defaults < file < env < CLI`` 優先序
堆疊並做深度 dict 合併,也無法回報*每個鍵由哪一層勝出*。本功能補上這個 12-factor 解析器。

純標準函式庫(``copy``);不匯入 ``PySide6``。各層為呼叫端提供的純 mapping(env 層由外部傳入,絕不
隱含讀取 ``os.environ``),因此解析在 CI 中具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import LayeredConfig, deep_merge

    cfg = (LayeredConfig()
           .add_layer("defaults", {"db": {"host": "local", "port": 5432}})
           .add_layer("file", file_values, priority=10)
           .add_layer("env", env_values, priority=20))

    settings = cfg.resolve()                  # {"db": {"host": ..., "port": ...}}
    host = cfg.get("db.host")
    trace = cfg.explain("db.host")            # SourceTrace(value=..., layer="env")

``add_layer`` 註冊一個具名層;``priority`` 越高越勝出(預設為插入順序,因此後加的層覆蓋先前的)。
``resolve`` 依優先序由低到高深度合併每一層 —— 巢狀 dict 遞迴合併,而純量與 list 直接取代。``get`` 以
點分鍵從解析後設定讀取並帶預設值;``explain`` 回傳 ``SourceTrace``,標明點分鍵的勝出層(不存在時拋
``KeyError``)。``deep_merge`` 另以獨立的雙 mapping 輔助函式提供。

執行器命令
----------

``AC_resolve_config`` 把 ``layers`` 清單(每筆 ``{name, mapping, priority?}``)深度合併成
``{config}``。``AC_explain_config`` 對點分 ``key`` 回傳 ``{trace}``(值與勝出層)。兩者皆以 MCP 工具
(``ac_resolve_config`` / ``ac_explain_config``)以及 Script Builder 中 **Data** 分類下的命令提供。
