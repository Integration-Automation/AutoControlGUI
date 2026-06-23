信任評分樣板比對(歧義 / PSR)
==============================

``match_template`` 只回傳最佳分數並直接點擊——但工具列中重複出現的控制項,或近乎相同的
同類元件,可能在*兩處*都相關到 ~0.95,因此高分**不代表**比對*無歧義*,比對器可能自信地
點錯目標。``match_with_trust`` 為像素樣板加入 Lowe 式比值測試(``feature_match`` 已對 ORB
關鍵點這麼做,但 ``match_template`` 從未如此):它檢視整個相關性曲面,比較全域峰值與排除
視窗外的次高峰,並計算峰值對旁瓣比(PSR),標記出強但有歧義的比對。

本功能重用 ``visual_match._score_map``——即公開比對器丟棄的完整 ``matchTemplate`` 曲面
——因此不重複任何比對程式。``haystack`` 可注入(ndarray / 路徑 / PIL);分析可在合成陣列上
單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import match_with_trust, score_peaks

    hit = match_with_trust("save_button.png", min_score=0.8)
    if hit and not hit.is_ambiguous:
        click(*hit.center)
    elif hit:
        print("有歧義!", hit.peak_ratio, "次高:", hit.second_score)

    # 只要指標,不要 match 物件
    print(score_peaks("icon.png"))   # {best, second, peak_ratio, psr, ambiguous, location}

``match_with_trust`` 回傳 ``TrustedMatch``(``x`` / ``y`` / ``width`` / ``height`` /
``score`` / ``scale`` / ``second_score`` / ``peak_ratio`` / ``psr`` / ``is_ambiguous`` +
``center``)或 ``None``。當次高峰至少達到最佳值的 ``ambiguous_ratio`` 倍(預設 0.9)時,
``is_ambiguous`` 為真。``psr`` 為峰值對旁瓣比(旁瓣完全平坦時為 ``None``)。``score_peaks``
僅回傳縮放 1.0 時的指標字典。

執行器指令
----------

``AC_match_with_trust``(``template`` / ``min_score`` / ``scales`` / ``ambiguous_ratio`` /
``region`` / ``method`` → ``{found, match}``)以 MCP 工具 ``ac_match_with_trust``(唯讀)及
Script Builder 指令 **Match Template (trust-scored)**(位於 **Image** 分類下)形式提供。
