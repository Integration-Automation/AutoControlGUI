統計與 A/B 顯著性
=================

``ab_locator`` 以原始成功率對策略排名,``run_history`` 儲存執行時長,但沒有任何東西計算百分位,
也無法告訴你某個差異是*統計上顯著*還是雜訊。本功能補上分析層:摘要統計、雙比例 z 檢定、Welch
t 檢定、Cohen's d,以及 2x2 卡方檢定。

常態 CDF 以 ``math.erf`` 精確計算;t 分布的 p 值使用正規化不完全 beta 函數,因此結果不需 SciPy
即可對齊參考實作。純標準函式庫;不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        describe, percentile, two_proportion_z_test, welch_t_test, cohens_d)

    describe([12.0, 9.5, 14.2, 11.1])
    # {"n": 4, "min": 9.5, "max": 14.2, "mean": 11.7, "stdev": ...,
    #  "p50": ..., "p90": ..., "p95": ..., "p99": ...}

    # B 變體的轉換率有比 A 好嗎?(90/200 vs 110/200)
    result = two_proportion_z_test(90, 200, 110, 200)
    # {"z": 2.0, "p_value": 0.0455, "significant": True,
    #  "diff": 0.1, "ci_low": ..., "ci_high": ...}

    # 連續型指標(例如延遲):B 與 A 是否不同?
    welch_t_test(a_samples, b_samples)        # {t, df, p_value, significant, ci}
    cohens_d(a_samples, b_samples)            # 效果量

``percentile`` 支援線性內插(預設)或最近秩;``describe`` 在常見動差之外加上 p50/p90/p95/p99。
``two_proportion_z_test`` 在檢定時使用合併標準誤、在信賴區間時使用未合併標準誤(教科書慣例)。
``welch_t_test`` 回報 Welch–Satterthwaite 自由度與精確的 t 分布 p 值。``chi_square_2x2`` 給出
df=1 的卡方(對同一張表等於 z 檢定的 ``z²``)。這些與 ``ab_locator`` 的計數及 ``run_history`` 的
時長自然搭配。

執行器命令
----------

``AC_describe_stats`` 接受 ``values``(數值清單或 JSON 字串),回傳摘要字典。
``AC_ab_significance`` 接受 ``a_conv`` / ``a_n`` / ``b_conv`` / ``b_n``,回傳雙比例 z 檢定結果。
兩者皆以 MCP 工具(``ac_describe_stats`` / ``ac_ab_significance``)以及 Script Builder 中
**Data** 分類下的命令提供。
