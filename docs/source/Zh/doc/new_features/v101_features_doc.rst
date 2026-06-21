單序列異常偵測
============

``data_drift`` 回答的是「兩個批次之間*分布*是否偏移」—— 無法指出單一即時序列中*哪一個*值異常 ——
而 ``slo.burn_alerts`` 只對錯誤預算燃燒設門檻,不針對任意度量值(延遲尖峰、成本尖峰、CPU)。本功能以
z-score、穩健的 MAD(modified z-score)與 EWMA 控制圖,在單一序列中標記離群值。

純標準函式庫(``math`` / ``statistics``);不匯入 ``PySide6``。每個函式皆為純函式(輸入值、輸出旗標),
因此在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import detect_anomalies, mad_anomalies, ewma_control

    series = [10, 11, 9, 10, 12, 10, 95, 11, 10]    # 索引 6 為尖峰
    mad_anomalies(series)                            # [6](穩健)
    detect_anomalies(series, method="mad")
    # [{index, value, score, is_anomaly}, ...]

    ewma_control(values, alpha=0.5, target_mean=10, target_sigma=1)  # 偏移索引

``detect_anomalies`` 為每個值評分(預設 ``mad``,或 ``zscore``)並標記超過門檻者(MAD 為 3.5、z-score
為 3.0)。``mad_anomalies`` / ``zscore_anomalies`` 只回傳被標記的索引,``mad_scores`` / ``zscore_scores``
回傳原始分數。MAD(Iglewicz-Hoaglin modified z-score)對離群值膨脹離散度具穩健性,因此在純 z-score 失靈
之處仍保持敏感。``ewma_control`` 是針對持續性水準偏移的 EWMA 控制圖 —— 傳入 ``target_mean`` /
``target_sigma`` 設定 in-control 基準(否則用序列自身統計)。

執行器命令
----------

``AC_detect_anomalies`` 接受 ``values`` 清單(可選 ``method`` / ``threshold``)回傳 ``{results}``。它以
MCP 工具 ``ac_detect_anomalies`` 以及 Script Builder 中 **Data** 分類下的命令提供。
