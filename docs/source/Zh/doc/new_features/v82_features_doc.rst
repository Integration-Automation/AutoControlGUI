分布漂移偵測
==========

``stats`` 具備針對 A/B *實驗*結果(比例與平均)的雙樣本檢定,但沒有 Population Stability Index,也沒有
Kolmogorov-Smirnov 雙樣本檢定來做經典的「今天的資料形狀是否與基準一致」檢查。本功能加入 PSI、KS,以及
與 ``data_profile`` 搭配的類別漂移摘要。

純標準函式庫(``math`` / ``bisect`` / ``collections`` + 重用 ``stats.percentile``);不匯入 ``PySide6``。
每個函式皆為純函式(輸入序列、輸出 dict/float),因此在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import psi, ks_two_sample, categorical_drift, detect_drift

    score = psi(reference, current)               # Population Stability Index
    ks = ks_two_sample(reference, current)        # {statistic, p_value}
    report = detect_drift(reference, current)     # {psi, drifted, ks}

    cat = categorical_drift(ref_labels, cur_labels)
    # {chi_square, total_variation, categories}

``psi`` 以 ``reference`` 的分位邊界將 ``current`` 分箱,並加總每箱的 log-ratio 貢獻(分布相同為 0,
分歧越大值越大)。``ks_two_sample`` 回傳最大經驗 CDF 差距與 Kolmogorov 分布的 p 值。``categorical_drift``
以卡方統計量與 total-variation 距離比較類別頻率。``detect_drift`` 把數值路徑包成一份報告,並以 ``threshold``
(預設 ``0.25``)給出 ``drifted`` 判定。

執行器命令
----------

``AC_detect_drift`` 接受 ``reference`` / ``current`` 數值清單(以及選用的 ``threshold`` / ``bins``)
回傳 ``{psi, drifted, ks}``。``AC_categorical_drift`` 回傳類別摘要。兩者皆以 MCP 工具
(``ac_detect_drift`` / ``ac_categorical_drift``)以及 Script Builder 中 **Data** 分類下的命令提供。
