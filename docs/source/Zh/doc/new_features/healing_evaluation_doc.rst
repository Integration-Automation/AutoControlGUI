固定影像定位器比較
==================

實驗性評估器讓各版本使用同一份不可變 PNG 輸入::

    from je_auto_control import evaluate_healing_manifest, write_healing_report

    report = evaluate_healing_manifest("benchmarks/self_healing/dataset.json")
    write_healing_report(report, "locator-comparison.json")
    write_healing_report(report, "locator-comparison.html")

``AC_self_heal_evaluate`` 與 MCP ``ac_self_heal_evaluate`` 都以 ``path`` 指定
相同的本機資料集。CLI 可從動作 JSON 檔執行該命令，Script Builder 也提供此命令。
**Self-Healing → 版本比較** 從「動作」選單提供背景比較、取消、案例／來源詳情與匯出。
切換資料集會丟棄舊結果，關閉面板會要求停止。

Schema 1 包含 ``samples`` 與 ``versions``。樣本欄位為 ``id``、``frame``，以及選填的
``expected_box``、``expected_miss``、``origin``、``scale``、``region``、``run_id``、
``step_id``。版本包含 ``template`` 與選填的 ``threshold``。
資產路徑相對於資料集目錄，不可透過路徑或符號連結越界；明確與外層日誌的路徑政策取交集。
上限為 1 MiB 資料集、每張 PNG 16 MiB／一千六百萬像素、合計 64 MiB 編碼資產，
以及 500 個樣本、32 個版本、10,000 組比較。

Box 採半開區間的邏輯螢幕座標，scale 是每邏輯單位的像素數，支援負原點與區域裁切。
未標註與預期 miss 分開計算。正確率以已標註樣本為分母，誤判以已標註且回傳座標的樣本為分母。
恢復成功必須同時有正確座標與明確的操作後驗證，分母為已知標註與驗證結果的後備嘗試。
所有比率附分子、分母，空集合顯示 null。離線策略不操作裝置，也不臆測驗證結果。
成本選填，單位為美元，另附已知成本筆數。報告不含 PNG 內容。

Python 可使用 ``EvaluationSample``、``TemplateFrameLocator``、``VLMFrameLocator``
與 ``evaluate_locators``。VLM 必須明確提供 backend，資料集入口不會自行選用。
測試只用受控 backend。錯誤與取消原樣傳遞，不會算成 miss；報告快照遮蔽本次執行
已解析的秘密值，不改動輸入。

固定合成資料集與預期母體位於 ``benchmarks/self_healing``，涵蓋樣板改版、miss、未標註、
負原點、兩倍縮放與裁切，不代表真實應用程式的正確率。p50／p95 是包含解碼與延遲匯入的
牆鐘耗時線性插值，未做暖機或機器校正；此資料集不支持速度改善的宣稱。
