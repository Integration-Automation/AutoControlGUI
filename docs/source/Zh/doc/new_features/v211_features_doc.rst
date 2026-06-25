依觀測時長自適應逾時
====================

寫死的等待是長年的不穩定來源:太短則慢機器與 UI 競速;太長則每次失敗都得付滿整個逾時。可長久的修法是
從某步驟*實際*花了多久來*學習*逾時。``adaptive_timeout`` 把一組觀測時長轉為穩健的逾時——取高百分位
(慢但真實的情況)乘上安全 ``factor``,再夾到合理的 ``[min_s, max_s]`` 區間。

* :func:`recommend_timeout` ——餵給等待或 ``GateConfig`` 的單一數值。
* :func:`timeout_stats` ——同上,但額外暴露百分位與夾值旗標以利記錄 / 調校。

兩者皆為純函式並重用 :func:`stats.percentile`;沒有樣本時退回 ``default_s``(或 ``min_s``)。
不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import recommend_timeout, timeout_stats

    # 對話框歷來出現所花的秒數:
    seen = [0.8, 1.1, 0.9, 3.2, 1.0, 1.3]

    recommend_timeout(seen)                 # 約 p95 * 1.5,夾到 [1, 60]
    recommend_timeout(seen, percentile_q=99.0, factor=2.0, max_s=30.0)

    timeout_stats(seen)
    # {'n': 6, 'p50': 1.05, 'p_high': 2.7..., 'percentile_q': 95.0,
    #  'recommended': 4.1..., 'floored': False, 'capped': False}

把建議值當作下一個 ``wait_for_*`` / actionability 閘的 ``timeout_s``,並隨樣本增長重新計算。
尚無樣本時,以 ``default_s`` 作為冷啟動值。

執行器指令
----------

``AC_adaptive_timeout``(``durations`` 加上 ``percentile_q`` / ``factor`` /
``min_s`` / ``max_s`` → ``{timeout_s}``)與 ``AC_timeout_stats``(同樣輸入 →
``{n, p50, p_high, percentile_q, recommended, floored, capped}``)。``durations``
接受 JSON 清單。皆以對應的唯讀 ``ac_*`` MCP 工具及 Script Builder 指令(位於 **Flow** 分類下)形式提供。
