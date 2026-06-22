ORB 特徵比對(對旋轉 / 縮放 / 主題穩健)
========================================

像素模板比對——``match_template``、``match_masked``——是把模板像素與螢幕做相關運算,因此目標一旦*旋轉*、
以未列出的倍率縮放、或重新上色(亮 / 暗主題、hover 狀態、不同外觀),就會失效。``feature_match`` 改為比對
*關鍵點*:以方向不變的二進位描述子(ORB)描述的特徵角點,再用 RANSAC 對一致的點擬合單應矩陣。它能在
旋轉、縮放與外觀變化下定位元素,並回傳四個投影角點以及做為內建信心訊號的內點數。

它在可注入的 ``haystack`` 影像(ndarray / 路徑 / PIL)上執行,因此可在無真實螢幕下對合成陣列做單元測試。
ORB、暴力比對器與 ``findHomography`` 皆屬於 OpenCV 核心(不需 contrib 模組);OpenCV + NumPy 透過
``je_open_cv`` 引入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import feature_match

    hit = feature_match("logo.png", min_inliers=12)
    if hit:
        click(*hit.center)            # 定位四邊形的中心
        print(hit.corners)            # 4 個 [x, y] 點,依模板順序
        print(hit.inliers, hit.score) # 幾何內點數與內點比例

``feature_match`` 回傳 ``FeatureMatch``(``corners``、``center``、``inliers``、``matches``、``score``),
或在幾何一致的比對少於 ``min_inliers`` 時回傳 ``None``。``ratio`` 是 Lowe 比例測試的門檻(越低越嚴格);
``max_features`` 限制 ORB 關鍵點預算。ORB 的邊界與 patch 尺寸會針對圖示大小的模板自動縮小,否則 OpenCV
的預設值會將其全數捨棄。

執行器命令
----------

``AC_feature_match`` 接受 ``template`` 以及 ``region`` / ``max_features`` / ``ratio`` / ``min_inliers``,
回傳 ``{found, match}``。它以 MCP 工具 ``ac_feature_match`` 以及 Script Builder 中 **Image** 分類下的命令提供。
