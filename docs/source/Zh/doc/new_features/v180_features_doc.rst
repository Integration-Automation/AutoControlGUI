比對前安定閘 + 命中穩定性
==========================

在動畫進行中比對是主要的不穩定來源:轉圈圖示還在轉、轉場做到一半,比對器命中暫態。
``smart_waits.wait_until_screen_stable`` 閘控*即時輪詢迴圈*並回傳布林——它無法對*可注入*的
幀序列評分穩定度,也無法告訴你某個*命中*是否跨幀維持。``match_stability`` 補上兩者,且作用於
注入幀因此可單元測試:``region_stability`` 以相鄰幀 SSIM 評分幀序列的安定度,``match_persistence``
檢查某 template 的命中是否跨幀維持在同一處(jitter 小),而非只在某一幸運幀。

本功能重用 ``ssim.ssim_compare``、``visual_match.match_template`` 與
``grounding_consensus.consensus_point``——不新增比對程式。幀可注入(ndarray / 路徑 / PIL)。
不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import region_stability, match_persistence

    frames = [grab(), grab(), grab()]   # 同一區域的幾張快照
    if region_stability(frames, settle_threshold=0.99)["stable"]:
        do_the_match()

    result = match_persistence("button.png", frames, min_score=0.8, agree_px=8)
    if result["persisted"]:
        print("穩定命中, jitter", result["jitter"])

``region_stability`` 回傳 ``{stable, mean_ssim, min_ssim}``——當最低相鄰幀 SSIM 超過
``settle_threshold`` 時 ``stable``。``match_persistence`` 回傳 ``{persisted, n_hits, jitter}``
——當 template 在*每一*幀都找到且命中中心於 ``agree_px`` 內一致時 ``persisted``(``jitter``
為其離散度;0 = 穩如磐石)。

執行器指令
----------

``AC_region_stability``(``frames`` / ``settle_threshold`` → ``{stable, mean_ssim, min_ssim}``)
與 ``AC_match_persistence``(``template`` / ``frames`` / ``min_score`` / ``agree_px`` →
``{persisted, n_hits, jitter}``)。兩者以 MCP 工具 ``ac_region_stability`` /
``ac_match_persistence``(唯讀)及 Script Builder 指令 **Region Stability (frames)** /
**Match Persistence (frames)**(位於 **Image** 分類下)形式提供。
