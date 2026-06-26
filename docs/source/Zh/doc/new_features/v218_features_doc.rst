把變化歸因到實際改變的元素
==========================

既有的 diff 回答「像素在*哪裡*改變」(``motion_regions``、``perceptual_diff``、
``ssim_changed_regions`` 回傳原始像素區域),或「哪些*無障礙*元素不同」(``element_diff``,需 a11y 中介資料)。
缺少的中段是:給定一個畫面 diff **與一份元素方框清單**,*那些*元素中哪些改變了?``change_localize`` 依
每個提供的方框改變多少評分並排序。

* :func:`rank_changes` ——純函式:接受 ``[{box, score}]`` 並把每個方框標記為 ``changed``
  (分數達到或超過 ``threshold``),依改變最多排在最前。
* :func:`localize_changes` ——把參考影像對目前螢幕做 diff,依每個元素方框的平均像素改變評分,再排序。

``cv2`` / ``numpy`` 採延遲匯入(模組無需它們即可匯入),載入器重用 :mod:`visual_match`。
排序為純函式且可完整測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import localize_changes, rank_changes, mark_elements

    boxes = [mark["bbox"] for mark in mark_elements(elements)]

    # 某動作後,那些元素中哪些真的改變了?
    changed = localize_changes("before.png", boxes, current="after.png")
    for entry in changed:
        if entry["changed"]:
            print("元素改變:", entry["box"], entry["score"])

    # 或自行排序預先算好的分數:
    rank_changes([{"box": [0, 0, 40, 20], "score": 0.6}], threshold=0.1)

``localize_changes`` 回傳 ``[{box, score, changed}]`` 依改變最多排序,``score`` 是方框的平均
逐像素改變(0..1)。它與 ``set_of_marks`` / 無障礙元素方框搭配,把原始螢幕 diff 轉成逐元素的
「什麼改變了」訊號——點擊後的 agent 回饋通道。

執行器指令
----------

``AC_localize_changes``(``reference`` 加上 ``boxes`` JSON 清單加上 ``current`` /
``threshold`` / ``region`` → ``{changes}``)與 ``AC_rank_changes``(``scored_boxes`` JSON 清單加上
``threshold`` → ``{changes}``,純函式)。皆以對應的唯讀 ``ac_*`` MCP 工具及 Script Builder 指令
(位於 **Image** 分類下)形式提供。
