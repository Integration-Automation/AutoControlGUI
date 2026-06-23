旋轉與縮放容忍的樣板比對
========================

``match_template`` 能跨*縮放*搜尋樣板(容忍 DPI / 縮放),但假設樣板為軸對齊——
OpenCV 的 ``matchTemplate`` 不具旋轉不變性,因此略為傾斜的控制項、旋轉的圖示,或
轉到不同角度的旋鈕 / 刻度盤都會比對失敗。``match_rotated`` 加入旋轉掃描:每個角度
以 ``cv2.warpAffine`` 套用到樣板上,並與 ``np.linspace`` 縮放空間交叉,回傳相關性
最高的(scale, angle)——因此呼叫端也能得知還原出的*姿態*。

本功能重用 ``visual_match`` 的灰階載入器、縮放 resize、相關性方法表與非極大值抑制,
不重複任何比對或幾何程式。``haystack`` 可注入(ndarray / 路徑 / PIL),因此搜尋可在
合成陣列上單元測試;只有預設(擷取螢幕)為裝置相依。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import match_rotated, match_rotated_all, scale_space

    # 尋找可能轉到任一角度、任一縮放的旋鈕
    hit = match_rotated("knob.png", angles=[-15, 0, 15, 30],
                        scales=scale_space(0.9, 1.1, 3), min_score=0.85)
    if hit:
        print(hit.angle, hit.scale, hit.score, hit.center)

    # 每個旋轉後的出現位置,重疊以 NMS 合併
    for m in match_rotated_all("arrow.png", angles=[0, 90, 180, 270]):
        print(m.center, m.angle)

``match_rotated`` 回傳單一 ``RotatedMatch``(``x`` / ``y`` / ``width`` / ``height`` /
``score`` / ``scale`` / ``angle`` + ``center``)或 ``None``;``match_rotated_all``
回傳所有達到 ``min_score`` 的命中,相鄰角度 / 縮放的重疊偵測以 NMS 合併,依分數排序。
``scale_space(min, max, steps)`` 為回傳等間距縮放的輔助函式。

執行器指令
----------

``AC_match_rotated``(``template`` / ``min_score`` / ``angles`` / ``scales`` /
``region`` / ``method`` → ``{found, match}``)與 ``AC_match_rotated_all``(另加
``max_results`` / ``nms_iou`` → ``{count, matches}``)。兩者以 MCP 工具
``ac_match_rotated`` / ``ac_match_rotated_all``(唯讀)及 Script Builder 指令
**Match Template (rotated)** / **Match Template All (rotated)**(位於 **Image**
分類下)形式提供。
