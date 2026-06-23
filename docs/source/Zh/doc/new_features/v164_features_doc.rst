自動門檻樣板比對(對分數圖做 Otsu)
====================================

每次呼叫 ``match_template_all`` 都迫使呼叫者猜 ``min_score``:太低會讓 NMS 充滿背景雜訊,
太高會漏掉縮放 / 換膚的目標,而正確值因素材與畫面而異。``match_autothresh`` 移除這個魔術
數字——它對*相關性分數直方圖*(而非像素強度,後者是 ``preprocess.binarize`` 的做法)套用
Otsu 法,找出「背景相關」團與「真正匹配」團之間的谷,並回傳該門檻加上一個 *separability*
(分離度)值,讓呼叫端知道何時直方圖為單峰(無明確匹配 → 不要信任該門檻)。

本功能重用 ``visual_match._score_map``(公開比對器丟棄的完整 ``matchTemplate`` 曲面)與
``cv2_utils.blobs.connected_boxes``——每個過門檻區域只回傳單一峰,避免原始像素掃描 + NMS
在寬相關峰上留下的重複命中。``haystack`` 可注入;分析可在合成陣列上單元測試。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import match_auto, auto_threshold

    # 無需手調 min_score——門檻由分數圖推導
    for hit in match_auto("save_button.png", floor=0.5):
        print(hit.center, hit.score)

    info = auto_threshold("save_button.png")
    # {"threshold": 0.83, "separability": 0.61, "n_above": 2}
    if info["separability"] < 0.3:
        print("無明確匹配——門檻不可信")

``match_auto`` 每個過門檻區域回傳一個 ``Match``,依分數排序並以 ``max_results`` 為上限;
門檻為 ``max(floor, otsu_threshold)``,使單峰 / 雜訊曲面無法把它拉到合理下限之下。
``auto_threshold`` 回傳 ``{threshold, separability, n_above}``——``separability`` 接近 0
表示分數直方圖為單峰,該門檻應視為不可靠。

執行器指令
----------

``AC_match_auto``(``template`` / ``floor`` / ``max_results`` / ``region`` / ``method`` →
``{count, matches}``)與 ``AC_auto_threshold``(``template`` / ``region`` / ``method`` →
``{found, info}``)。兩者以 MCP 工具 ``ac_match_auto`` / ``ac_auto_threshold``(唯讀)及
Script Builder 指令 **Match Template (auto-threshold)** / **Auto Threshold (Otsu on scores)**
(位於 **Image** 分類下)形式提供。
