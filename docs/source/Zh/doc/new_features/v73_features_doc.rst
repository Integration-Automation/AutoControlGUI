串流延遲百分位
=============

``stats.percentile`` 精確,但需要把整份已排序的樣本清單放在記憶體中;對長時間執行或分片的
load / soak 測試,你會想要一個每筆 O(1)、記憶體有界、且**可合併**的結構。本功能補上 HdrHistogram
風格的 :class:`LatencyDigest`(以有效位數分桶記錄、可跨分片合併),外加供小樣本集使用的
:func:`exact_percentiles`。

純標準函式庫(``math``);不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import LatencyDigest, exact_percentiles

    digest = LatencyDigest(sig_figs=3)
    for latency_ms in stream:
        digest.record(latency_ms)        # O(1)、記憶體有界
    print(digest.summary())              # min/mean/max/p50/p90/p95/p99

    # 把各分片的 digest 合併成一個
    total = shard_a.merge(shard_b)

    # 小樣本集的精確百分位
    exact_percentiles([12.0, 9.5, 14.2], qs=(50, 95))

``LatencyDigest.record`` 把每個值四捨五入到 ``sig_figs`` 有效位數分桶(因此記憶體由相異捨入值的
數量決定,而非樣本數);``percentile`` / ``quantiles`` / ``summary`` 讀回,而 ``merge`` 把另一個
digest 折入以做跨分片彙整 —— 這正是從各 worker 結果計算正確彙整 p99 所需的特性。
``exact_percentiles`` 在小樣本集情況下委派給 ``stats.percentile``。

執行器命令
----------

``AC_percentiles`` 接受 ``samples``(清單或 JSON 字串)與選用的 ``qs`` 分位(預設 50/90/95/99),
回傳 ``{percentiles}``。同一操作亦以 MCP 工具 ``ac_percentiles`` 以及 Script Builder 中
**Report** 分類下的命令提供。
