Set-of-Marks 標籤佈局(不重疊、可讀顏色)
=========================================

Set-of-Marks 在每個元素上疊一個編號標籤,讓視覺模型能說「點 7」。``set_of_marks`` 以固定偏移繪製
每個標籤,故在密集 UI 上數字會互相疊壓(難以辨讀),而深色標籤在深色元素上會消失。``marks_layout``
以純幾何修正兩者。

* :func:`place_labels` ——貪婪式不重疊放置:對每個 mark,在其方框周圍嘗試一圈候選位置
  (上、下、內;左/右對齊),取第一個仍在邊界內且不與任何已放置標籤重疊者。
* :func:`label_color` ——挑選標籤文字顏色(黑或白),取對元素背景 WCAG 對比較佳者。

純標準函式庫;重用 :func:`a11y_audit.contrast_ratio`。無需繪製即可完整測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import mark_elements, place_labels, label_color

    marks = mark_elements(elements)            # [{id, bbox, ...}]
    layout = place_labels(marks, bounds=(1920, 1080))
    # [{'id': 1, 'label': [x, y, 22, 16], 'anchor': [bx, by]}, ...]

    label_color((30, 30, 30))     # {'rgb': [255, 255, 255], 'contrast': ...}

把 :func:`place_labels` 產生的 ``label`` 方框餵給你的繪製器(取代固定偏移),並用 :func:`label_color`
挑選每個編號的顏色,使其在背景上維持可讀。``place_labels`` 是確定性的且依輸入 marks 排序,
故同一畫面總是以相同方式編號。

執行器指令
----------

``AC_place_labels``(``marks`` JSON 清單加上 ``label_width`` / ``label_height`` /
``bounds`` ``[w, h]`` → ``{labels}``)與 ``AC_label_color``(``background``
``[r, g, b]`` → ``{rgb, contrast}``)。皆以對應的唯讀 ``ac_*`` MCP 工具及 Script Builder 指令
(位於 **Image** 分類下)形式提供。
