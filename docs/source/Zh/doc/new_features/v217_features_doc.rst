主題不變比對(淺色模板、深色模式)
==================================

``match_template`` 以原始像素強度相關比對,故在淺色模式擷取的模板,對深色模式下同一控制項評分極差——
極性反轉了。修法是比較*結構*(邊緣、梯度),不論顏色走向如何皆相同。``theme_normalize`` 在比對前
把影像轉成極性不變的表示。

* :func:`normalize_theme` ——把影像映射為正規化的單通道影像。``sobel``(預設)與 ``laplacian``
  使用梯度幅值,對影像與其顏色反相版本相同;``zscore`` 將強度標準化。
* :func:`match_theme` ——對模板與 haystack(預設為螢幕)都做 :func:`normalize_theme`,再定位模板——
  即使在會擊敗原始比對的淺/深主題切換下也能找到。

``cv2`` / ``numpy`` 採延遲匯入,故匯入本模組永遠不需要它們,定位邏輯則重用
:func:`visual_match.match_template`。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import match_theme, normalize_theme

    # 淺色模式擷取的按鈕模板,在深色模式的 app 中找到:
    hit = match_theme("save_button_light.png", method="sobel", min_score=0.4)
    if hit and hit["score"] >= 0.5:
        click(hit["x"] + hit["width"] // 2, hit["y"] + hit["height"] // 2)

    # 轉換本身(例如餵給你自己的比對器):
    edges = normalize_theme("template.png", method="sobel")

由於梯度幅值對影像與其反相版本相同,``normalize_theme(img, "sobel")`` 等於
``normalize_theme(255 - img, "sobel")``——正是這個不變性讓單一模板能比對兩種主題。
``min_score`` 請設得比原始比對低(結構相關分數較低)。

執行器指令
----------

``AC_match_theme``(``template`` 加上 ``region`` ``[x, y, w, h]`` / ``method`` /
``min_score`` → ``{found, x, y, width, height, score}``)跨主題切換定位模板。以對應的唯讀
``ac_match_theme`` MCP 工具及 Script Builder 指令(位於 **Image** 分類下)形式提供。
:func:`normalize_theme`(回傳影像陣列)則是 Python API 介面。
