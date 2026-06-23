Grounding 自我一致性(提案共識)
================================

一個目標可同時以多種方式 grounding——set-of-marks、OCR、樣板比對、a11y 樹,或模型的 N 次
抽樣——而它們未必一致。``ab_locator`` / ``element_scoring`` 依歷史可靠度排序定位器*策略*,
卻從不把*同時*的提案融合成單一共識點並附離散度指標;``action_grounding.snap_to_element``
把*單一*座標貼到最近元素,沒有「不一致」的概念。``grounding_consensus`` 將候選點聚類(或對
候選元素投票),回傳一致同意的目標加上 *agreement* 比例與 *spread*,並標記低一致度目標,
讓呼叫端可改為放大 / 詢問人工,而非盲目點擊。

純標準函式庫幾何;確定性、可在無裝置下單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import consensus_point, consensus_element, is_confident

    proposals = [[480, 260], [484, 258], [477, 263], [900, 100]]  # 一個離群
    result = consensus_point(proposals, cluster_radius=24)
    if is_confident(result, min_agreement=0.6):
        click(*result.point)
    else:
        print("提案不一致:", result.agreement, result.spread)

    # 或把提案投票到已知元素清單
    element, agreement = consensus_element(proposals, elements)

``consensus_point`` 將 ``[x, y]`` 或 ``[x, y, weight]`` 候選聚類,回傳 ``ConsensusResult``
(``point`` / ``agreement``——勝出群權重佔總權重 / ``spread`` / ``n_clusters``),空輸入回傳
``None``。``consensus_element`` 把每個提案投到最近元素,回傳 ``(element, agreement)``。
``is_confident`` 對 agreement 設門檻。

執行器指令
----------

``AC_consensus_point``(``candidates`` / ``cluster_radius`` → ``{found, result}``)與
``AC_consensus_element``(``candidates`` / ``elements`` → ``{found, element, agreement}``)。
兩者以 MCP 工具 ``ac_consensus_point`` / ``ac_consensus_element``(唯讀)及 Script Builder 指令
**Grounding Consensus Point** / **Grounding Consensus Element**(位於 **Native UI** 分類下)
形式提供。
