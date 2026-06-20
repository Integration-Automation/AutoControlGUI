感知雜湊影像去重
================

螢幕錄影或步驟報告常含有許多近乎相同的畫面。感知雜湊(average-hash 與 difference-hash)
將視覺上相似的影像對應到數值接近的指紋,因此可依漢明距離分群並收合 —— 每個明顯不同的
畫面只保留一個代表。

雜湊函式使用 **Pillow**(已是核心相依 —— 無需額外套件);去重/比較邏輯為純 Python,且
``hasher`` 可注入,因此分群可在無任何影像下單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        average_hash, dhash, hamming_distance, images_similar, dedupe_images)

    h1 = average_hash("frame1.png")          # 十六進位指紋
    h2 = average_hash("frame2.png")
    hamming_distance(h1, h2)                  # 相異的位元數
    images_similar(h1, h2, max_distance=5)   # 是否在容差內?

    dedupe_images(["a.png", "b.png", "c.png"], max_distance=5)
    # -> 每個近似重複叢集保留一張(保留第一個)

``average_hash`` 將每個像素與平均亮度比較;``dhash`` 將每個像素與其右鄰比較(對 gamma
偏移更穩健)。``dedupe_images`` 接受 ``hasher`` 掛鉤(預設為 ``average_hash``),因此可
用預先計算的雜湊測試分群。

執行器指令
----------

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_image_hash``                影像的 ``{hash}``(``algo``:average/dhash)。
``AC_dedupe_images``             收合近似重複影像後的 ``{unique}``。
================================ ===================================================

``paths`` 接受清單或 JSON 字串清單(因此視覺化建構器可用)。相同操作亦提供為 MCP 工具
(``ac_image_hash`` / ``ac_dedupe_images``),以及 Script Builder 中 **Image** 分類下的
指令。
