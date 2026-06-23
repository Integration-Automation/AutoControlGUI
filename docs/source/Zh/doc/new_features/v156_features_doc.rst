加權候選評分
============

``anchor_locator`` 以單一空間關係過濾、依距離排序,``ab_locator`` 競賽*整個策略*並依耗時挑選——兩者都不是把角色
匹配、模糊名稱相似度、對錨點的鄰近度與啟用狀態合成單一信心的*加權多訊號評分器*。當多個框都可能是目標時,
自我修復 / grounding 正需要這個。名稱相似度可注入(預設為專案的 ``fuzzy_ratio``),因此不新增字串距離程式。

純標準函式庫,作用於純元素字典(``role`` / ``name`` / ``x`` / ``y`` / ``width`` / ``height`` / 選用 ``enabled``),
完全可單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import score_candidates, best_candidate

    ranked = score_candidates(candidates, want_role="button", want_name="Save",
                              anchor=(960, 540))
    for c in ranked:
        print(round(c.score, 3), c.element["name"], c.matched_on)

    pick = best_candidate(candidates, want_role="button", want_name="Save")
    if pick:
        click(*[pick.element["x"], pick.element["y"]])

``score_candidates`` 回傳 ``ScoredCandidate`` 清單(``element`` / ``score`` / ``matched_on`` 明細),最佳優先;每個
啟用的訊號貢獻 0..1,分數為其平均。``want_role`` 在角色精確匹配時得 1、``want_name`` 執行 ``name_similarity``
(預設 ``fuzzy_ratio``)、``anchor`` 加入鄰近項、``prefer_enabled`` 獎勵啟用元素。``best_candidate`` 回傳最佳者
(或 ``None``)。

執行器命令
----------

``AC_score_candidates``(``candidates`` / ``want_role`` / ``want_name`` / ``anchor`` → ``{count, scored}``)與
``AC_best_candidate``(相同輸入 → ``{found, best}``)。它們以 MCP 工具 ``ac_score_candidates`` / ``ac_best_candidate``
以及 Script Builder 中 **Native UI** 分類下的命令提供。
