自我修復定位器回寫
==================

自我修復定位器會在執行期於新位置找到元素並記錄該次修復 —— 但*修正後*的位置隨即被丟棄,
因此下次執行又得從頭修復。``RepairStore`` 補上這個迴圈:它記錄該次修復的修正定位器(座
標 / VLM 描述 / 方法),在信心足夠高時**自動套用**,否則排入*待審建議*。之後的執行可透過
:meth:`RepairStore.resolved` 讀取已學到的修正。

JSON 後端(透過共用 ``json_store`` 助手);純標準函式庫;信心與門檻皆為明確值,因此行為
具確定性且可完整單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import RepairStore, repair_from_heal

    store = RepairStore("repairs.json")
    # 高信心修復 -> 立即套用:
    store.record("login_btn", method="vlm", coordinates=[120, 64],
                 description="Login", confidence=0.95)
    store.resolved("login_btn")        # -> {method, coordinates, description}

    # 低信心修復 -> 排入審查:
    s = store.record("save_btn", method="image", coordinates=[5, 5],
                     confidence=0.5)
    store.pending()                    # -> [save_btn 建議]
    store.approve(s.id)                # 此後 store.resolved("save_btn") 可用

    # 直接從 HealEvent(物件或 dict):
    repair_from_heal(heal_event, "login_btn", store=store, confidence=0.9)

``record`` 在 ``confidence >= auto_threshold``(預設 0.9)時自動套用,否則建立 ``pending``
建議;``approve`` / ``reject`` 決定佇列中的項目;``resolved(key)`` 回傳最新已套用/已核准的
修正定位器(或 ``None``)—— 供未來執行重用而不必重新修復的持久修正。

執行器指令
----------

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_repair_record``             保存修正定位器(自動套用或排入佇列)。
``AC_repair_resolved``           取得某鍵已學到的修正定位器。
``AC_repair_pending``            列出待審的建議。
``AC_repair_approve``            核准一個待審建議。
================================ ===================================================

相同操作亦提供為 MCP 工具(``ac_repair_*``),以及 Script Builder 中 **Tools** 分類下的指
令。
