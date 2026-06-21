服務等級目標(SLO)
==================

框架會發出原始訊號(``observability`` 指標、``run_history`` 時長),但沒有把它們轉成 SLO、錯誤
預算或燃燒率警示的運維層。本功能補上:在一段視窗的結果紀錄上計算 SLI、對目標計算錯誤預算,以及
Google SRE workbook 的**多視窗多燃燒率**警示。

紀錄是純資料(``[{"timestamp": float, "ok": bool}, ...]``),因此整體離線且具決定性;時鐘可注入。
純標準函式庫;不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import evaluate_slo, burn_alerts

    report = evaluate_slo(records, target=0.99)
    # {"sli": 0.995, "good": 995, "total": 1000, "target": 0.99,
    #  "budget_total": 10.0, "budget_remaining": 5.0,
    #  "budget_remaining_fraction": 0.5, "burn_rate": 0.5}

    for alert in burn_alerts(records, target=0.99):
        page_oncall(alert)        # severity、threshold、long/short 燃燒率

``evaluate_slo`` 計算 SLI(good / total)、錯誤預算(``(1 - target) * total`` 個事件)與燃燒率
(``bad_rate / (1 - target)`` —— 1.0 代表剛好按進度消耗預算,> 1 代表太快)。``burn_rate`` 是某
視窗的純數字。``burn_alerts`` 評估 :func:`default_burn_rules` 的標準 Google SRE 分層 —— 1h(與
5m)達 14.4× 呼叫、6h(與 30m)達 6× 呼叫、3d(與 6h)達 1× 開票 —— 且只有當某層的長視窗與短視窗
**雙雙**超過門檻時才觸發,以取得快速重置與少量誤報。可傳入自訂的 ``rules``(``BurnRule`` 清單)。

執行器命令
----------

``AC_evaluate_slo`` 接受 ``records``(清單或 JSON 字串)、``target`` 與選用的 ``window_s``,回傳
SLI/預算報告。``AC_burn_alerts`` 回傳 ``{alerts, firing}``。兩者皆以 MCP 工具(``ac_evaluate_slo``
/ ``ac_burn_alerts``)以及 Script Builder 中 **Report** 分類下的命令提供。
