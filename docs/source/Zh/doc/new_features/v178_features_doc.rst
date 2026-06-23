多模板共識比對
==============

一個按鈕常以多種狀態呈現——預設 / 懸停 / 按下 / 停用——但它是單一邏輯目標。``ab_locator``
A/B 測試*哪個單一策略勝出*,``match_template(scales=...)`` 跨縮放掃描*一個*模板——兩者都不把
*多個參考裁切*融合成一次投票。``match_ensemble`` 比對每個參考,聚類命中中心,只有在至少
``min_votes`` 個參考於 ``agree_px`` 內一致時才接受目標——大幅減少換膚 / 動畫 UI 上的誤判。

投票核心(``vote_centers``)為純標準函式庫,並重用 ``grounding_consensus`` 做聚類,因此可在
無影像下單元測試;只有 ``match_ensemble`` 本身呼叫 ``visual_match.match_template``(可於注入的
合成 ``haystack`` 上測試)。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import match_ensemble, vote_centers

    # 同一按鈕的三個參考裁切(預設 / 懸停 / 按下)
    result = match_ensemble(["btn_default.png", "btn_hover.png", "btn_pressed.png"],
                            min_score=0.8, agree_px=10, min_votes=2)
    if result:
        click(*result["point"])     # {point, votes, n_candidates, spread}

    # 或對你已有的命中中心投票
    vote_centers([[100, 100], [102, 98], [400, 400]], agree_px=10, min_votes=2)

``match_ensemble`` 回傳共識位置的 ``{point, votes, n_candidates, spread}``,或在少於
``min_votes`` 個參考一致時回傳 ``None``。``vote_centers`` 是對你提供的候選中心的純投票步驟。

執行器指令
----------

``AC_match_ensemble``(``templates`` / ``min_score`` / ``agree_px`` / ``min_votes`` /
``region`` → ``{found, result}``)與 ``AC_vote_centers``(``centers`` / ``agree_px`` /
``min_votes`` → ``{found, result}``)。兩者以 MCP 工具 ``ac_match_ensemble`` /
``ac_vote_centers``(唯讀)及 Script Builder 指令 **Match Ensemble (vote references)** /
**Vote Centers (consensus)**(位於 **Image** 分類下)形式提供。
