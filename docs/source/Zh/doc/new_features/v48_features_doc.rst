環境範圍的具型別資產儲存
========================

流程需要集中管理、依環境(dev/staging/prod)而異且帶有型別的設定值 —— 這是 orchestrator
的「Assets / lockers」支柱。密鑰保險庫只處理密鑰,config-sync 搬移整塊設定;兩者皆無具
型別、依環境的具名查詢。``AssetStore`` 補足此處:值依環境儲存、讀回時做型別轉換,而
``credential`` 資產持有一個*參照*(密鑰名稱),由 :meth:`resolve` 透過注入的解析器轉成
真實值 —— 因此密鑰永不出現在純 ``get`` 或 executor 紀錄中。

JSON 後端(或記憶體內);純標準函式庫;不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import AssetStore, active_environment

    store = AssetStore("assets.json")
    store.set("max_retries", 3, asset_type="int", environment="prod")
    store.set("api_base", "https://prod.example.com", environment="prod")
    store.set("db_password", "vault_db_pw", asset_type="credential")  # value = 參照

    store.get("max_retries", environment="prod").value     # -> 3(具型別)
    store.get("api_base", environment="staging").value     # -> 退回 default
    store.get("db_password").value                         # -> "vault_db_pw"(參照,安全)

    # 透過注入的密鑰解析器解析 credential(僅限 Python):
    store = AssetStore("assets.json", secret_resolver=secret_manager.get)
    store.resolve("db_password")                           # -> 真實密鑰

型別為 ``text`` / ``int`` / ``bool`` / ``credential``;``get`` 會轉成宣告型別,並在未停用
時退回 ``default`` 環境。``active_environment()`` 讀取 ``JE_AUTOCONTROL_ENV``。``list`` /
``delete`` 補齊整個儲存體。

執行器指令
----------

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_set_asset``                 儲存具型別、依環境的資產。
``AC_get_asset``                 讀取資產(credential 維持參照)。
``AC_list_assets``               列出 ``{name, type, environment}``(不含值)。
================================ ===================================================

credential 的**解析**刻意僅限 Python API(因此密鑰永不進入執行紀錄)。相同的生命週期操
作亦提供為 MCP 工具(``ac_set_asset`` / ``ac_get_asset`` / ``ac_list_assets``),以及
Script Builder 中 **Data** 分類下的指令。
