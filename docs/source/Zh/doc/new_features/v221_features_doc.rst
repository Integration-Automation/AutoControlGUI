在視野內操作——捲動到目標,再於可操作時動作
============================================

兩個可靠性原語原本各自獨立:``scroll_find.scroll_until_visible`` 把螢幕外的目標捲進畫面,
``actionability.act_when_ready`` 則在目標可見 / 穩定 / 啟用 / 未被遮擋前等待再動作。真實的
「點選下三頁的那一列」步驟需要*兩者*——先捲到它,再閘控後才點擊。``act_in_view`` 把它們組合成單一呼叫。

* :class:`ScrollPlan` ——把捲動搜尋(``kind`` / ``direction`` / ``max_scrolls`` /
  ``scroll_amount``)與其可注入的 ``locator`` / ``scroller`` 接縫打包,讓組合後的呼叫維持在合理的參數數量內。
* :func:`act_in_view` ——捲動直到找到目標,接著在其位置執行 actionability 閘控,並對其執行 ``action``。

每個接縫——捲動的 locator / scroller、action、actionability 探針(``region_sampler`` /
``enabled_probe`` / ``hit_tester``)與閘控 ``config``——皆可注入,故整個流程能在沒有螢幕的情況下測試。
重用 :func:`scroll_find.scroll_until_visible` 與 :func:`actionability.act_when_ready`。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import act_in_view, ScrollPlan

    # 向下捲動到「Submit」按鈕影像,於可操作時點擊
    act_in_view("submit.png", lambda point: click(point[0], point[1]),
                scroll=ScrollPlan(kind="image", direction="down",
                                  max_scrolls=20))

``act_in_view`` 回傳 ``{acted, coords, scrolls, result}``(``result`` 為 action 的回傳值),
若目標始終未進入畫面則丟出 ``AutoControlActionException``。傳入 ``enabled_probe`` / ``hit_tester`` /
``config`` 可讓 actionability 閘控真正等到控制項已啟用且未被遮擋才觸發動作——否則一旦定位到目標即動作。

執行器指令
----------

``AC_act_in_view``(``target`` 加上 ``kind`` / ``direction`` / ``max_scrolls`` /
``scroll_amount`` / ``button`` → ``{acted, coords, scrolls}``)把 template 或文字目標捲入畫面並點擊。
以對應的 ``ac_act_in_view`` MCP 工具及 Script Builder 指令(位於 **Flow** 分類下)形式提供。
:func:`act_in_view`(接受任意 action 與 actionability 探針)則是 Python API 介面。
