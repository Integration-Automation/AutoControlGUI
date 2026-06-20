座標空間對映(模型網格 ⇄ 實體像素)
====================================

電腦操作 / VLA 模型並不是以實體像素點擊。Anthropic 建議將螢幕截圖縮小到 XGA
(~1024×768)再把點擊映射回去;Gemini 的電腦操作模型回傳正規化的 **1000×1000** 網格;
其他模型則假設你宣告的顯示尺寸。``CoordinateSpace`` 捕捉實體解析度與模型網格並雙向轉
換,因此 agent loop 可餵給模型一張尺寸正確的截圖,並把它的點擊轉回真實座標。

對映為純算術(無相依);:func:`downscale_png` 使用 Pillow(已是核心相依)。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        CoordinateSpace, xga_space, normalized_space, downscale_png)

    space = normalized_space(1920, 1080, grid=1000)   # Gemini 式 1000x1000
    space.to_physical(500, 500)        # -> (960, 540)   模型點擊 -> 真實像素
    space.to_model(960, 540)           # -> (500, 500)   真實像素 -> 模型網格

    xga = xga_space(2560, 1440)        # Anthropic 式縮小,保持長寬比
    small_png = downscale_png(screenshot_png, xga)   # 把這張送給模型

``xga_space`` 會保持長寬比且永不放大;``normalized_space`` 建立方形網格。
``to_physical`` / ``to_model`` 皆會四捨五入並夾限到有效的像素/網格範圍內。

執行器指令
----------

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_to_physical``               將模型網格 ``(x, y)`` 對映到實體像素。
``AC_to_model``                  將實體像素對映到模型網格(反向)。
================================ ===================================================

兩者皆接受 ``x, y, physical_w, physical_h, model_w, model_h`` 並回傳 ``{x, y}``。相同操
作亦提供為 MCP 工具(``ac_to_physical`` / ``ac_to_model``),以及 Script Builder 中
**Agent** 分類下的指令。
