時間序列轉換
==========

``observability`` 的計數器與量規只儲存*當前*值 —— 沒有任何東西能把計數器轉成每秒速率 —— 而
``cost_telemetry`` 只以固定的「天」分桶。本功能在 ``(timestamp, value)`` 序列上加入 Prometheus 風格的
``rate`` / ``irate`` / ``increase`` / ``delta``(具重置感知),以及 tumbling-bucket ``downsample`` 與
網格 ``resample``。

純標準函式庫(``bisect``);不匯入 ``PySide6``。不讀取 wall clock —— 視窗使用序列自身的時間戳 —— 因此每個
函式皆完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import ts_rate, ts_increase, ts_downsample, ts_resample

    series = [(0, 0), (10, 50), (20, 120)]      # (timestamp_s, counter_value)
    ts_rate(series)                              # 6.0(20 秒內 120)
    ts_rate(series, window_s=10)                 # 只看最後 10 秒的速率
    ts_increase(series)                          # 120.0(重置感知)

    ts_downsample([(0, 1), (3, 3), (5, 10)], 5, "avg")   # [(0, 2.0), (5, 10.0)]
    ts_resample([(0, 0), (20, 20)], 10, fill="linear")   # [(0,0),(10,10),(20,20)]

``ts_rate`` / ``ts_increase`` 把值下降視為計數器重置(Prometheus 語意);``ts_irate`` 是最後兩個樣本的
瞬時速率;``ts_delta`` / ``ts_idelta`` 是量規的首尾差與最後兩點差。``ts_downsample`` 把序列滾成 ``bucket_s``
的 tumbling 桶,以 ``avg`` / ``sum`` / ``min`` / ``max`` / ``first`` / ``last`` / ``count`` 聚合。
``ts_resample`` 對齊到固定網格,以 ``"last"``(前向填補)、``"linear"``(內插)或 ``None``(留缺)填值。

執行器命令
----------

``AC_ts_rate`` 對 ``series``(可選 ``window_s``)回傳 ``{rate}``;``AC_ts_downsample`` 對 ``series`` 與
``bucket_s``(可選 ``agg``)回傳 ``{buckets}``。兩者皆以 MCP 工具(``ac_ts_rate`` / ``ac_ts_downsample``)
以及 Script Builder 中 **Data** 分類下的命令提供。
