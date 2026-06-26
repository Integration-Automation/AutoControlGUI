免模板元素提案(像素到元素)
============================

Set-of-Marks、``observation`` 與 grounding 輔助函式都假設你已有一份元素方框清單——但在框架無法
建模的畫面上(遊戲、自繪 app、遠端桌面),並沒有無障礙樹可提供。``element_proposal`` 從像素建立
這份漏斗頂端清單:偵測候選*控制項*方框(封閉邊緣 blob)與*文字*方框
(:func:`text_regions.find_text_regions`),將兩者融合——丟棄其實只是文字的控制項方框——
並依閱讀順序回傳,每個標記為 ``text`` 或 ``widget``。

* :func:`propose_elements` ——完整的像素到元素管線。
* :func:`tag_kinds` ——純函式:依來源把融合後的方框標記 ``text`` / ``widget``,並保留其閱讀順序 ``index``。

融合 / 交叉檢查 / 排序重用 :mod:`element_parse`——``ocr`` > ``icon`` 來源優先序*即*「丟棄其實是
文字的控制項」檢查——文字偵測則重用 :mod:`text_regions`。``cv2`` 採延遲匯入,故模組仍可匯入;
:func:`tag_kinds` 為純函式且可完整測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import propose_elements, mark_elements

    # 沒有無障礙樹?直接從畫面提案元素:
    elements = propose_elements(min_area=120)
    # [{'box': [x, y, w, h], 'kind': 'widget', 'index': 0}, ...]

    # 像任何元素清單一樣餵給 Set-of-Marks:
    marks = mark_elements(elements)

``propose_elements`` 依閱讀順序回傳 ``[{box, kind, index}]``,``kind`` 為 ``text`` 或 ``widget``。
它是 agent 堆疊在未建模 UI 上缺少的漏斗頂端:像素進、乾淨的編號元素清單出,可供標記、observation
或 grounding。以 ``min_area`` 調整你在意的最小控制項,以 ``iou_threshold`` 調整重疊文字與控制項
方框合併的積極程度。

執行器指令
----------

``AC_propose_elements``(``region`` ``[x, y, w, h]`` / ``min_area`` /
``iou_threshold`` → ``{elements}``)在畫面上執行完整管線,``AC_tag_kinds``
(``elements`` JSON 清單 → ``{elements}``,純函式)則標記預先融合的清單。皆以對應的唯讀
``ac_*`` MCP 工具及 Script Builder 指令(位於 **Image** 分類下)形式提供。
