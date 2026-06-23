可串接 / 可過濾的候選定位器
============================

``anchor_locator`` 解析單一錨點→目標關係,``grid_locator`` 定址網格儲存格;兩者都不支援對候選集合做*可組合的細化*
——``.within(panel).filter(has_text="Delete").nth(2)``——這是 Selenium-4 / Playwright 的串接並過濾定位慣用法。
目前細化得重新查詢後端。本功能是對來自*任何*來源(模板比對、OCR、a11y 樹、:doc:`v138_features_doc`)的框做純
後置過濾。

``Candidates`` 包裝一串 ``{x, y, width, height, …}`` 框;每個方法都回傳*新的* ``Candidates``,因此鏈式呼叫無副作用
且完全可單元測試。純標準函式庫,不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import from_boxes

    target = (from_boxes(boxes)                    # 來自任何定位器的框
              .within((0, 0, 1920, 120))           # 只取工具列
              .filter(has_text="Delete")           # 只取刪除按鈕
              .sort_reading()                       # 由左到右
              .nth(1))                              # 第二個
    if target.center():
        click(*target.center())

``within(region)`` 保留中心落在矩形內的框;``filter`` 保留符合所有條件的框(``has_text`` 子字串、``near``
``(x, y, max_dist)`` 鄰近、``min_area`` / ``max_area``,或任意 ``predicate``);``sort_reading`` 排序;
``nth`` / ``first`` / ``last`` 選取;``resolve()`` 回傳存活清單、``center()`` 回傳第一個框的中心。鏈式呼叫永不
變動原集合。

執行器命令
----------

``AC_locate_chain`` 對 ``boxes`` 陣列依序套用一串 JSON ``ops``——``{op:"within",region:[…]}``、
``{op:"filter",has_text:…}``、``{op:"reading"}``、``{op:"nth",index:…}``、``{op:"first"}``、``{op:"last"}``——
回傳 ``{count, boxes, center}``。它以 MCP 工具 ``ac_locate_chain`` 以及 Script Builder 中 **Image** 分類下的命令提供。
