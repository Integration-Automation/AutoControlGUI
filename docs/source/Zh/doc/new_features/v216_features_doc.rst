取樣區域的文字對比(WCAG)
==========================

:func:`a11y_audit.contrast_ratio` 對你已知的前景 / 背景配對評分。但當你只有螢幕上的一個*區域*——
一個按鈕、一個標籤——你並不知道那兩個顏色;你有的是一片像素。``contrast_map`` 補上這道缺口:
把取樣區域拆成其主要前景(少數——通常是文字)與背景(多數)顏色,再評其 WCAG 對比。

* :func:`grade_contrast` ——純函式:把前景 / 背景配對對 WCAG 2.x 門檻轉為
  ``{ratio, aa, aaa, aa_large, aaa_large}``。
* :func:`dominant_pair` ——純函式:依亮度把一串取樣 RGB 像素拆成主要的 ``{foreground, background}``。
* :func:`region_contrast` ——取樣螢幕區域並評分,透過可注入的 ``sampler``(預設為真實螢幕擷取)。

評分與拆分皆為純函式並重用 :func:`a11y_audit.contrast_ratio`,故能在沒有螢幕的情況下完整測試。
不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import grade_contrast, dominant_pair, region_contrast

    # 若你已知顏色:
    grade_contrast((90, 90, 90), (255, 255, 255))
    # {'ratio': 3.9, 'aa': False, 'aaa': False, 'aa_large': True, ...}

    # 若你只有螢幕的一個區域,取樣並評分:
    report = region_contrast(region=[x, y, w, h])
    if not report["aa"]:
        print("低對比文字", report["foreground"], report["background"])

``dominant_pair`` 以平均亮度切分取樣像素,把較大的一群視為背景、較小的視為文字——
均勻一片會讓兩者得到相同顏色(無對比)。``region_contrast`` 接受可注入的 ``sampler``
(``region -> RGB 像素清單``),故邏輯能在沒有真實螢幕的情況下測試。

執行器指令
----------

``AC_grade_contrast``(``foreground`` / ``background`` ``[r, g, b]`` → 評分)、
``AC_dominant_pair``(``pixels`` JSON 清單 ``[r, g, b]`` → ``{foreground, background}``)與
``AC_region_contrast``(``region`` ``[x, y, w, h]`` → 評分 + 顏色 + ``samples``)。皆以對應的
唯讀 ``ac_*`` MCP 工具及 Script Builder 指令(位於 **Image** 分類下)形式提供。
