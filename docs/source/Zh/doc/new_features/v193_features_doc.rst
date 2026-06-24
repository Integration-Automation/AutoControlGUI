不穩定測試的共同失敗分群
========================

不穩定(flaky)測試很少是獨立的:搖晃的共用 fixture、緩慢的相依、或吵雜的環境,會讓*一群*測試在
相同的執行中一起失敗(研究發現約 75% 的 flaky 測試落在共同失敗的群集裡)。逐一以翻轉率排名測試
會錯過這個共同根因。``flake_cluster`` 量測每對測試多常在*相同*執行中失敗——即各自失敗的執行集合
之間的 Jaccard 相似度——並把共同失敗超過門檻的測試分群,讓你能追一個根因,而非 N 個症狀。

* :func:`cofailure_pairs` ——共同失敗超過門檻的測試對,
* :func:`failure_clusters` ——共同失敗測試的連通群集,附凝聚度分數(群內平均成對 Jaccard)。

輸入是一份執行清單,每個元素為該次執行中失敗的測試名稱集合。純標準庫;不涉及裝置,不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import failure_clusters, cofailure_pairs

    runs = [["test_a", "test_b"],            # 這次執行兩者皆失敗
            ["test_a", "test_b"],
            ["test_c"],
            ["test_a", "test_b", "test_c"]]

    failure_clusters(runs, threshold=0.6)
    # [{"tests": ["test_a", "test_b"], "size": 2, "cohesion": 1.0}]

    cofailure_pairs(runs, threshold=0.6)
    # [{"tests": ["test_a", "test_b"], "jaccard": 1.0, "co_failures": 3}]

``threshold`` 是連結兩測試所需的最小共同失敗 Jaccard;``min_size``(預設 ``2``)會丟棄單例,
讓只有真正的群集浮現。群集以最大 / 最凝聚者在前回傳。

執行器指令
----------

``AC_failure_clusters``(``runs`` / ``threshold`` / ``min_size``)與
``AC_cofailure_pairs``(``runs`` / ``threshold``)。皆以唯讀 ``ac_*`` MCP 工具及 Script Builder
指令(位於 **Testing** 分類下)形式提供。
